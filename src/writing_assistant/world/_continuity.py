"""Persistent world runs with explicit configuration and caller-supplied decisions."""
from __future__ import annotations

from copy import deepcopy
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from ._simulation import WorldSimulation, SimulationError, make_proposal

SCHEMA = "lotus-continuity-run/1"
ROSTER_SCHEMA = "lotus-continuity-run/2"
CONFIG_SCHEMA = "lotus-continuity-config/2"
# Exact source bindings supported for read-only access; never migrated implicitly.
LEGACY_SOURCES = {"runner": "e950cb9e404721b28b6d12f9b73e652516850f958d2a0a1c60b6b9640f907d41",
                  "core": "999781be4163b4d5ff789baa8fd9cf5affbe469435ec97e600045bccf19462e5"}
PREVIOUS_SOURCES = {"runner": "b127d11de49ceca6181ff466ac34e0addf72a50e49c136dc1c8001302af4b44e",
                    "core": "c35f69544b8e2cd435d4f9cef7702e2e63f791a4ffa3d43f0bb10cfbd58b4eb2",
                    "life": "b43ee214d2a550118316384d40d051bdd684ff33dc8d15748d9ffc11687e03f6"}
MAX_BYTES = 16 * 1024 * 1024
LIMIT = 24
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
EXECUTED = Path(__file__).read_bytes()
CORE = Path(__file__).with_name("_simulation.py")
CORE_EXECUTED = CORE.read_bytes()
LIFE = Path(__file__).with_name("_life.py")
LIFE_EXECUTED = LIFE.read_bytes()
ACTIONS = {"wait": {"type"}, "take": {"type", "item"}, "unlock": {"type", "door"},
           "move": {"type", "to"}, "trade": {"type", "item", "seller", "price"},
           "share": {"type", "fact", "to"}}


class ContinuityError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(value, code="invalid_bundle"):
    if not value:
        raise ContinuityError(code)


def canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
        need(len(raw) <= MAX_BYTES, "size_limit")
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ContinuityError("invalid_json") from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decode(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            need(key not in out, "duplicate_key")
            out[key] = value
        return out
    try:
        need(len(raw) <= MAX_BYTES, "size_limit")
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContinuityError("invalid_json")))
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise ContinuityError("invalid_json") from None


def fields(value, names):
    need(type(value) is dict and set(value) == set(names))


def slug(value):
    return type(value) is str and SLUG.fullmatch(value) is not None


def action_valid(action):
    need(type(action) is dict and type(action.get("type")) is str
         and action["type"] in ACTIONS and set(action) == ACTIONS[action["type"]], "invalid_action")
    for key, value in action.items():
        if key not in {"type", "price"}:
            need(slug(value), "invalid_action")
    if "price" in action:
        need(type(action["price"]) is int and 0 < action["price"] <= 10**9, "invalid_action")
    return deepcopy(action)


def source_sha():
    need(Path(__file__).read_bytes() == EXECUTED and CORE.read_bytes() == CORE_EXECUTED
         and LIFE.read_bytes() == LIFE_EXECUTED, "source_changed")
    return {"runner": hashlib.sha256(EXECUTED).hexdigest(), "core": hashlib.sha256(CORE_EXECUTED).hexdigest(),
            "life": hashlib.sha256(LIFE_EXECUTED).hexdigest()}


def request_limit(config):
    return config["request_limit"] if config.get("schema") == CONFIG_SCHEMA else LIMIT


def scheduled_actor(config, turn):
    """One scheduling rule for execution, recovery and bundle validation."""
    order = config["actor_order"]
    return order[turn % len(order)]


def config_schema(config):
    return ROSTER_SCHEMA if config.get("schema") == CONFIG_SCHEMA else SCHEMA


def _validate_config(config):
    modern = type(config) is dict and config.get("schema") == CONFIG_SCHEMA
    names = {"scenario", "profiles", "actor_order", "policy", "turn_limit"}
    fields(config, names | ({"schema", "request_limit"} if modern else set()))
    WorldSimulation(config["scenario"], max_requests=request_limit(config))
    actors = set(config["scenario"]["actors"])
    order = config["actor_order"]
    need(type(order) is list and all(slug(x) for x in order)
         and 1 <= len(order) <= 32 and len(set(order)) == len(order)
         and set(order) <= actors, "invalid_roster")
    if not modern:
        need(len(actors) == 4 and set(order) == actors)
    need(type(config["profiles"]) is dict and set(config["profiles"]) == set(order))
    need(type(config["turn_limit"]) is int
         and 1 <= config["turn_limit"] <= (256 if modern else 16))
    need(config["policy"] in ({"external"} if modern else {"profile", "garden"}))
    if modern:
        need(type(config["request_limit"]) is int and 1 <= config["request_limit"] <= 256)
    names = {"actor_id", "version", "aim", "values", "risk", "habit"}
    if not modern:
        names |= {"destination", "reserve_coins", "independent_key", "collect_key",
                  "share_to", "accompany", "witness_before_cross"}
    for actor, p in config["profiles"].items():
        fields(p, names)
        need(p["actor_id"] == actor and type(p["version"]) is int
             and p["version"] == (2 if modern else 1))
        need(all(type(p[x]) is str and 0 < len(p[x]) <= 2000 for x in ["aim", "risk", "habit"]))
        need(type(p["values"]) is list and 1 <= len(p["values"]) <= 16
             and all(type(x) is str and 0 < len(x) <= 200 for x in p["values"]))
        if not modern:
            need(p["destination"] in config["scenario"]["locations"]
                 and type(p["reserve_coins"]) is int and 0 <= p["reserve_coins"] <= 10**9)
            need(all(type(p[x]) is bool for x in ["independent_key", "collect_key", "witness_before_cross"]))
            need(all(p[x] is None or p[x] in actors and p[x] != actor for x in ["share_to", "accompany"]))


def validate_config(config):
    try:
        return _validate_config(config)
    except ContinuityError:
        raise
    except SimulationError as exc:
        raise ContinuityError(exc.code) from None
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        raise ContinuityError("invalid_bundle") from None


def payload_for(request, profile, trajectory):
    return deepcopy({"identity": {k: v for k, v in request.items() if k not in {"completion_capability", "observation"}},
                     "profile": profile, "trajectory": trajectory, "observation": request["observation"]})


def trajectory_entry(job):
    p, o, action, receipt = job["payload"]["profile"], job["payload"]["observation"], job["action"], job["receipt"]
    location, coins = o["actor"]["location"], o["actor"]["coins"]
    if receipt["status"] == "accepted":
        if action["type"] == "move":
            location = action["to"]
        if action["type"] == "trade":
            coins -= action["price"]
    events = [e["event_id"] for e in o["events"]]
    if receipt["event_id"] is not None:
        events.append(receipt["event_id"])
    if p["version"] == 2:
        return {"request_id": job["request"]["request_id"], "version": receipt["version"],
                "action": deepcopy(action), "status": receipt["status"], "source_events": events,
                "profile_fields": ["aim", "values", "risk", "habit"],
                "observed_change": {"location": location, "coins": coins}}
    return {"request_id": job["request"]["request_id"], "version": receipt["version"],
            "action": deepcopy(action), "status": receipt["status"], "source_events": events,
            "profile_fields": ["destination", "reserve_coins", "independent_key", "collect_key", "share_to", "accompany", "witness_before_cross"],
            "goal_progress": {"location": location, "coins": coins, "at_destination": location == p["destination"]}}


def branch_data(world, profiles, trajectories=None, parent=None, cursor=0):
    return {"checkpoint": world.checkpoint(), "profiles": deepcopy(profiles),
            "trajectories": deepcopy(trajectories or {k: [] for k in profiles}), "jobs": {},
            "completion_order": [], "cursor": cursor, "parent": parent}


def _validate_bundle(data):
    fields(data, {"schema", "run_id", "source_sha", "config", "config_sha256", "issued", "allocations", "branches"})
    need(data["schema"] == config_schema(data["config"]) and slug(data["run_id"]))
    need(data["source_sha"] in (source_sha(), PREVIOUS_SOURCES) or
         data["schema"] == SCHEMA and data["source_sha"] == LEGACY_SOURCES, "source_binding")
    validate_config(data["config"])
    need(data["config_sha256"] == digest(data["config"]), "config_binding")
    need(type(data["branches"]) is dict and "main" in data["branches"] and 1 <= len(data["branches"]) <= 3)
    need(type(data["issued"]) is int and 0 <= data["issued"] <= request_limit(data["config"])
         and type(data["allocations"]) is list and len(data["allocations"]) == data["issued"])
    allocations = []
    worlds = {name: WorldSimulation.from_checkpoint(b["checkpoint"]) for name, b in data["branches"].items()}
    for name, b in data["branches"].items():
        fields(b, {"checkpoint", "profiles", "trajectories", "jobs", "completion_order", "cursor", "parent"})
        world = worlds[name]
        snap = world.snapshot()
        need(slug(name) and snap["state"]["branch_id"] == name and b["profiles"] == data["config"]["profiles"])
        need(type(b["jobs"]) is dict and type(b["completion_order"]) is list and type(b["cursor"]) is int
             and 0 <= b["cursor"] <= data["config"]["turn_limit"])
        if name == "main":
            need(b["parent"] is None)
            need(world.recording()["seed"]["state"] == data["config"]["scenario"])
            seed_history = {actor: [] for actor in b["profiles"]}
            seed_issued, seed_cursor = 0, 0
        else:
            parent = b["parent"]
            fields(parent, {"branch_id", "checkpoint", "trajectories", "cursor"})
            need(parent["branch_id"] in worlds and parent["branch_id"] != name)
            old = WorldSimulation.from_checkpoint(parent["checkpoint"])
            old_record, now_record = old.recording(), worlds[parent["branch_id"]].recording()
            need(old_record["seed"] == now_record["seed"]
                 and now_record["commands"][:len(old_record["commands"])] == old_record["commands"])
            need(old.fork(name).recording()["seed"] == world.recording()["seed"])
            seed_history, seed_issued, seed_cursor = parent["trajectories"], old.budget["issued"], parent["cursor"]
            for actor, rows in seed_history.items():
                need(data["branches"][parent["branch_id"]]["trajectories"][actor][:len(rows)] == rows)
        need(snap["budget"]["limit"] == request_limit(data["config"]))
        need(snap["budget"]["issued"] == seed_issued + len(b["jobs"]))
        commands = world.recording()["commands"]
        need(b["completion_order"] == [c["proposal"]["request_id"] for c in commands if c["kind"] == "resolve"])
        need(len(b["completion_order"]) == len(set(b["completion_order"])))
        history = deepcopy(seed_history)
        fixture_done = []
        for request_id in b["completion_order"]:
            job = b["jobs"][request_id]
            need(job["stage"] == "resolved")
            actor = job["request"]["actor_id"]
            need(job["payload"] == payload_for(job["request"], b["profiles"][actor], history[actor]))
            history[actor].append(trajectory_entry(job))
            if job["fixture_turn"] is not None:
                fixture_done.append(job["fixture_turn"])
        need(b["trajectories"] == history and fixture_done == list(range(seed_cursor, b["cursor"])))
        pending = {}
        for request_id, job in b["jobs"].items():
            fields(job, {"request", "payload", "payload_sha256", "stage", "action", "receipt", "fixture_turn"})
            request = job["request"]
            need(request["request_id"] == request_id and request["branch_id"] == name)
            actor = request["actor_id"]
            need(actor in b["profiles"] and job["payload_sha256"] == digest(job["payload"]))
            need(job["payload"]["profile"] == b["profiles"][actor]
                 and job["payload"]["observation"] == request["observation"])
            need(job["stage"] in {"prepared", "dispatching", "result-recorded", "resolved"})
            if job["fixture_turn"] is not None:
                turn = job["fixture_turn"]
                need(type(turn) is int and 0 <= turn < data["config"]["turn_limit"]
                     and actor == scheduled_actor(data["config"], turn))
            if job["stage"] == "resolved":
                need(job["receipt"] == snap["receipts"][request_id]["result"])
                need(snap["receipts"][request_id]["request"] == request)
                need(digest(make_proposal(request, action_valid(job["action"]))) == snap["receipts"][request_id]["proposal_sha256"])
            else:
                pending[request_id] = request
                need(job["receipt"] is None and job["payload"] == payload_for(request, b["profiles"][actor], history[actor]))
                need(job["fixture_turn"] is None or job["fixture_turn"] == b["cursor"])
                if job["stage"] == "result-recorded":
                    action_valid(job["action"])
                else:
                    need(job["action"] is None)
            allocations.append((name, request_id))
        need(snap["pending"] == pending)
    need(len(allocations) == len(set(allocations)) == data["issued"])
    declared = []
    for row in data["allocations"]:
        fields(row, {"branch_id", "request_id"})
        declared.append((row["branch_id"], row["request_id"]))
    need(len(declared) == len(set(declared)) and set(declared) == set(allocations))
    return data


def validate_bundle(data):
    try:
        return _validate_bundle(data)
    except ContinuityError:
        raise
    except SimulationError as exc:
        raise ContinuityError(exc.code) from None
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        raise ContinuityError("invalid_bundle") from None


def checked_path(root):
    path = Path(root).absolute()
    need(path == path.resolve(), "unsafe_path")
    for part in [path, *path.parents]:
        if part.exists():
            need(not part.is_symlink() and part.is_dir(), "unsafe_path")
    return path


class RunStore:
    """A trusted owner; actor clients receive serialized projections only."""
    def __init__(self, root, run_id, *, create=False, config=None, hook=None):
        need(slug(run_id), "invalid_run_id")
        if create:
            need(type(config) is dict and config.get("schema") == CONFIG_SCHEMA
                 and config.get("policy") == "external", "unsupported_world_config")
            validate_config(config)
        self.root, self.run_id, self.hook = checked_path(root), run_id, hook
        self.path = self.root / run_id
        self.fd, self.data, self.broken = None, None, False
        self.directory_identity = None
        self.creating, self.initial_config = create, deepcopy(config)

    def __enter__(self):
        try:
            if self.creating:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                try:
                    self.path.mkdir(mode=0o700)
                except FileExistsError:
                    raise ContinuityError("run_exists") from None
            need(self.path.is_dir() and not self.path.is_symlink(), "missing_run")
            need(self.path == self.path.resolve() and stat.S_IMODE(self.path.stat().st_mode) & 0o077 == 0, "unsafe_path")
            directory_info = self.path.stat()
            self.directory_identity = (directory_info.st_dev, directory_info.st_ino)
            flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
            self.fd = os.open(self.path / ".owner.lock", flags, 0o600)
            info = os.fstat(self.fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) & 0o077 == 0, "unsafe_lock")
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContinuityError("owner_busy") from None
            current = (self.path / ".owner.lock").lstat()
            need((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino), "unsafe_lock")
            if self.creating:
                config = self.initial_config
                validate_config(config)
                world = WorldSimulation(config["scenario"], max_requests=request_limit(config))
                data = {"schema": config_schema(config), "run_id": self.run_id, "source_sha": source_sha(),
                        "config": config, "config_sha256": digest(config), "issued": 0, "allocations": [],
                        "branches": {"main": branch_data(world, config["profiles"])}}
                self._save(data, "created")
            else:
                p = self.path / "bundle.json"
                info = p.lstat()
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not p.is_symlink()
                     and stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_size <= MAX_BYTES, "unsafe_bundle")
                fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as f:
                    opened = os.fstat(f.fileno())
                    need((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino)
                         and opened.st_nlink == 1 and opened.st_size <= MAX_BYTES, "unsafe_bundle")
                    raw = f.read(MAX_BYTES + 1)
                envelope = decode(raw)
                fields(envelope, {"schema", "payload", "sha256"})
                need(envelope["schema"] in {SCHEMA, ROSTER_SCHEMA}, "unsupported_bundle")
                need(envelope["schema"] == envelope["payload"].get("schema"), "unsupported_bundle")
                need(envelope["sha256"] == digest(envelope["payload"]), "bundle_digest")
                self.data = validate_bundle(envelope["payload"])
                need(self.data["run_id"] == self.run_id, "run_binding")
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _active(self):
        need(self.fd is not None and not self.broken, "owner_closed")
        need(self.path == self.path.resolve() and not self.path.is_symlink(), "unsafe_path")
        directory_info = self.path.stat()
        need((directory_info.st_dev, directory_info.st_ino) == self.directory_identity, "owner_replaced")
        locked, current = os.fstat(self.fd), (self.path / ".owner.lock").lstat()
        need((locked.st_dev, locked.st_ino) == (current.st_dev, current.st_ino)
             and stat.S_ISREG(current.st_mode) and current.st_nlink == 1, "unsafe_lock")
        source_sha()

    def _point(self, name):
        if self.hook:
            self.hook(name)

    def _save(self, data, label):
        self._active()
        try:
            need(data["source_sha"] == source_sha(), "legacy_source_read_only")
            validate_bundle(data)
            raw = canonical({"schema": data["schema"], "payload": data, "sha256": digest(data)})
            target = self.path / "bundle.json"
            if target.exists() or target.is_symlink():
                info = target.lstat()
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not target.is_symlink(), "unsafe_bundle")
            temporary = self.path / (".bundle-" + secrets.token_hex(12) + ".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            self._point("before_" + label + "_replace")
            self._active()
            os.replace(temporary, target)
            directory = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                try:
                    os.fsync(directory)
                except OSError as exc:
                    if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                        raise
            finally:
                os.close(directory)
            self.data = deepcopy(data)
            self._point("after_" + label + "_replace")
        except Exception:
            self.broken = True
            raise

    def snapshot(self):
        self._active()
        return deepcopy(self.data)

    def actor_view(self, actor_id, branch_id="main"):
        self._active()
        need(branch_id in self.data["branches"], "unknown_branch")
        b = self.data["branches"][branch_id]
        observation = WorldSimulation.from_checkpoint(b["checkpoint"]).observation(actor_id)
        return deepcopy({"actor_id": actor_id, "profile": b["profiles"].get(actor_id),
                         "trajectory": b["trajectories"].get(actor_id, []), "observation": observation})

    def advance_time(self, target, *, event_limit=16, branch_id="main"):
        self._active()
        need(not any(job["stage"] != "resolved" for branch in self.data["branches"].values()
                     for job in branch["jobs"].values()), "pending_request")
        need(branch_id in self.data["branches"], "unknown_branch")
        d = deepcopy(self.data)
        world = WorldSimulation.from_checkpoint(d["branches"][branch_id]["checkpoint"])
        result = world.advance_time(target, event_limit=event_limit)
        d["branches"][branch_id]["checkpoint"] = world.checkpoint()
        self._save(d, "time_advanced")
        return result

    def materialize(self, group_id, member_id, actor_id, *, observer, cause_id, branch_id="main"):
        self._active()
        need(not any(job["stage"] != "resolved" for branch in self.data["branches"].values()
                     for job in branch["jobs"].values()), "pending_request")
        need(branch_id in self.data["branches"], "unknown_branch")
        d = deepcopy(self.data)
        world = WorldSimulation.from_checkpoint(d["branches"][branch_id]["checkpoint"])
        result = world.materialize(group_id, member_id, actor_id, observer=observer, cause_id=cause_id)
        d["branches"][branch_id]["checkpoint"] = world.checkpoint()
        self._save(d, "materialized")
        return result

    def prepare(self, actor_id, request_id=None, branch_id="main", fixture_turn=None):
        self._active()
        need(branch_id in self.data["branches"], "unknown_branch")
        b = self.data["branches"][branch_id]
        need(actor_id in b["profiles"], "actor_not_selected")
        request_id = request_id or "request-" + str(self.data["issued"] + 1).zfill(3)
        need(slug(request_id), "invalid_request_id")
        if request_id in b["jobs"]:
            job = b["jobs"][request_id]
            need(job["request"]["actor_id"] == actor_id and job["fixture_turn"] == fixture_turn, "request_conflict")
            need(job["stage"] != "resolved", "request_closed")
            return deepcopy(job["payload"])
        need(self.data["issued"] < request_limit(self.data["config"]), "budget_exhausted")
        d = deepcopy(self.data)
        b = d["branches"][branch_id]
        world = WorldSimulation.from_checkpoint(b["checkpoint"])
        request = world.request(actor_id, request_id)
        payload = payload_for(request, b["profiles"][actor_id], b["trajectories"][actor_id])
        b["checkpoint"] = world.checkpoint()
        b["jobs"][request_id] = {"request": request, "payload": payload, "payload_sha256": digest(payload),
            "stage": "prepared", "action": None, "receipt": None, "fixture_turn": fixture_turn}
        d["issued"] += 1
        d["allocations"].append({"branch_id": branch_id, "request_id": request_id})
        self._save(d, "prepared")
        return deepcopy(payload)

    def _job(self, request_id, branch_id):
        need(branch_id in self.data["branches"], "unknown_branch")
        need(request_id in self.data["branches"][branch_id]["jobs"], "unknown_request")
        return self.data["branches"][branch_id]["jobs"][request_id]

    def dispatch(self, request_id, branch_id="main", client=None):
        self._active()
        job = self._job(request_id, branch_id)
        if job["stage"] == "resolved":
            return deepcopy(job["receipt"])
        if job["stage"] == "result-recorded":
            return self._finish(request_id, branch_id)
        need(job["stage"] != "dispatching", "uncertain_request")
        need(callable(client), "decision_client_required")
        d = deepcopy(self.data)
        d["branches"][branch_id]["jobs"][request_id]["stage"] = "dispatching"
        self._save(d, "dispatching")
        self._point("before_client")
        raw = canonical(job["payload"])
        result = client(raw)
        self._point("after_client")
        return self.record_result(request_id, result, branch_id)

    def record_result(self, request_id, action, branch_id="main"):
        self._active()
        action = action_valid(action)
        job = self._job(request_id, branch_id)
        need(job["stage"] != "prepared", "not_dispatched")
        if job["action"] is not None:
            need(job["action"] == action, "result_conflict")
            return deepcopy(job["receipt"]) if job["stage"] == "resolved" else self._finish(request_id, branch_id)
        d = deepcopy(self.data)
        job = d["branches"][branch_id]["jobs"][request_id]
        job["action"], job["stage"] = action, "result-recorded"
        self._save(d, "result_recorded")
        return self._finish(request_id, branch_id)

    def _finish(self, request_id, branch_id):
        d = deepcopy(self.data)
        b = d["branches"][branch_id]
        job = b["jobs"][request_id]
        world = WorldSimulation.from_checkpoint(b["checkpoint"])
        receipt = world.resolve(make_proposal(job["request"], job["action"]))
        job["receipt"], job["stage"] = receipt, "resolved"
        b["checkpoint"] = world.checkpoint()
        b["completion_order"].append(request_id)
        b["trajectories"][job["request"]["actor_id"]].append(trajectory_entry(job))
        if job["fixture_turn"] is not None:
            need(job["fixture_turn"] == b["cursor"], "turn_conflict")
            b["cursor"] += 1
        self._save(d, "resolved")
        return deepcopy(receipt)

    def step(self, actor_id, branch_id="main", client=None):
        need(callable(client), "decision_client_required")
        p = self.prepare(actor_id, branch_id=branch_id)
        return self.dispatch(p["identity"]["request_id"], branch_id, client)

    def run(self, branch_id="main", client=None):
        need(callable(client), "decision_client_required")
        self._active()
        need(branch_id in self.data["branches"], "unknown_branch")
        while self.data["branches"][branch_id]["cursor"] < self.data["config"]["turn_limit"]:
            b = self.data["branches"][branch_id]
            turn = b["cursor"]
            actor = scheduled_actor(self.data["config"], turn)
            request_id = "turn-" + str(turn).zfill(2)
            if request_id not in b["jobs"]:
                self.prepare(actor, request_id, branch_id, fixture_turn=turn)
            else:
                need(b["jobs"][request_id]["fixture_turn"] == turn, "turn_conflict")
            self.dispatch(request_id, branch_id, client)
        return self.summary()

    def fork(self, new_branch_id, parent="main"):
        self._active()
        need(slug(new_branch_id) and new_branch_id not in self.data["branches"], "invalid_branch")
        need(parent in self.data["branches"] and len(self.data["branches"]) < 3, "branch_limit")
        d = deepcopy(self.data)
        b = d["branches"][parent]
        world = WorldSimulation.from_checkpoint(b["checkpoint"]).fork(new_branch_id)
        parent_record = {"branch_id": parent, "checkpoint": b["checkpoint"],
                         "trajectories": deepcopy(b["trajectories"]), "cursor": b["cursor"]}
        d["branches"][new_branch_id] = branch_data(world, b["profiles"], b["trajectories"], parent_record, b["cursor"])
        self._save(d, "forked")
        return new_branch_id

    def replay(self):
        self._active()
        validate_bundle(deepcopy(self.data))
        return self.snapshot()

    def summary(self):
        self._active()
        out = {"run_id": self.run_id, "issued": self.data["issued"], "remaining": request_limit(self.data["config"]) - self.data["issued"], "branches": {}}
        for name, b in self.data["branches"].items():
            state = WorldSimulation.from_checkpoint(b["checkpoint"]).snapshot()["state"]
            out["branches"][name] = {"version": state["version"], "cursor": b["cursor"],
                "actors": {a: {"location": x["location"], "coins": x["coins"]} for a, x in state["actors"].items()}}
        return out
