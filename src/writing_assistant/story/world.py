"""Explicit narrative time, scoped actor observations and replayable choices."""
import argparse
import copy
import json
from pathlib import Path

from . import records, world_life


COMMANDS = {"world"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS world_runs (name TEXT PRIMARY KEY, spec BLOB NOT NULL, seed TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS world_branches (
    run TEXT NOT NULL REFERENCES world_runs(name), branch TEXT NOT NULL, parent TEXT, fork_revision INTEGER,
    head INTEGER NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(run,branch),
    FOREIGN KEY(run,parent) REFERENCES world_branches
);
CREATE TABLE IF NOT EXISTS world_events (
    run TEXT NOT NULL, branch TEXT NOT NULL, revision INTEGER NOT NULL, body BLOB NOT NULL,
    previous TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(run,branch,revision),
    FOREIGN KEY(run,branch) REFERENCES world_branches
);
CREATE TABLE IF NOT EXISTS world_checkpoints (
    run TEXT NOT NULL, branch TEXT NOT NULL, name TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL,
    PRIMARY KEY(run,branch,name), FOREIGN KEY(run,branch) REFERENCES world_branches
);
CREATE TABLE IF NOT EXISTS world_requests (
    run TEXT NOT NULL, id TEXT NOT NULL, branch TEXT NOT NULL, actor TEXT NOT NULL, revision INTEGER NOT NULL,
    packet BLOB NOT NULL, stage TEXT NOT NULL, choice TEXT, receipt BLOB, PRIMARY KEY(run,id),
    FOREIGN KEY(run,branch) REFERENCES world_branches
);
"""


def obj(value, keys, required=()):
    if type(value) is not dict or value.keys() - set(keys) or set(required) - value.keys():
        raise ValueError("Unexpected or missing fields in the world specification.")
    return value


def facts(value):
    if type(value) is not dict:
        raise ValueError("World facts must map names to text.")
    for key, val in value.items():
        records.nonempty(key)
        records.nonempty(val)
    return value


def validate_effects(effects, actors):
    if not isinstance(effects, list):
        raise ValueError("Expected a list of world effects.")
    for effect in effects:
        obj(effect, ("to", "facts"), ("to", "facts"))
        if not isinstance(effect["to"], str) or effect["to"] not in {"public", *actors}:
            raise ValueError("World effect has an unknown recipient.")
        facts(effect["facts"])


def spec_from(path):
    spec = obj(json.loads(path.read_bytes()), ("actors", "public", "schedule", "request_limit", "life"), ("actors",))
    actors = spec["actors"]
    if type(actors) is not dict or not 1 <= len(actors) <= 32 or "public" in actors:
        raise ValueError("Specify 1–32 named actors. The name public is reserved.")
    for name, actor in actors.items():
        records.nonempty(name)
        obj(actor, ("profile", "knowledge", "actions"), ("profile",))
        records.nonempty(actor["profile"])
        facts(actor.get("knowledge", {}))
        actions = actor.get("actions", {})
        if not isinstance(actions, dict):
            raise ValueError("Actor actions must map keys to authored choices.")
        for key, action in actions.items():
            records.nonempty(key)
            obj(action, ("label", "effects", "requires"), ("label", "effects"))
            conditions = facts(action.get("requires", {}))
            if any(key.partition(".")[0] not in ("public", "knowledge") or not key.partition(".")[2]
                   for key in conditions):
                raise ValueError("Action conditions may use only public or actor knowledge fields.")
            records.nonempty(action["label"])
            validate_effects(action["effects"], actors)
    facts(spec.get("public", {}))
    schedule = spec.get("schedule", [])
    if not isinstance(schedule, list) or len(schedule) > 128:
        raise ValueError("Schedule must be a list of timed effects.")
    last = 0
    for event in schedule:
        obj(event, ("at", "effects"), ("at", "effects"))
        if type(event["at"]) is not int or not max(1, last) <= event["at"] <= 1000000:
            raise ValueError("Supply scheduled minutes 1–1000000 in chronological order.")
        last = event["at"]
        validate_effects(event["effects"], actors)
    limit = spec.get("request_limit", 256)
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError("Request limit must be 1–256.")
    if "life" in spec:
        world_life.validate(spec["life"], actors)
    return spec


def initial(spec):
    state = {"minute": 0, "public": copy.deepcopy(spec.get("public", {})),
            "trajectory": {actor: [] for actor in spec["actors"]}, "actors": {
        name: copy.deepcopy(actor.get("knowledge", {})) for name, actor in spec["actors"].items()
    }}
    if "life" in spec:
        state["life"] = world_life.initial(spec["life"])
    return state


def choices(spec, state, actor):
    visible = {"public": state["public"], "knowledge": state["actors"][actor]}
    offered = {}
    for key, action in spec["actors"][actor].get("actions", {}).items():
        for field, expected in action.get("requires", {}).items():
            section, _, name = field.partition(".")
            if visible[section].get(name) != expected:
                break
        else:
            offered[key] = action
    return offered


def deliver(state, effects):
    for effect in effects:
        recipient = effect["to"]
        target = state["public"] if recipient == "public" else state["actors"][recipient]
        target.update(effect["facts"])


def apply(state, spec, event):
    if event["kind"] == "advance-time":
        target = event["minute"]
        limit = event.get("event_limit", 128)
        if (type(target) is not int or type(limit) is not int or not 0 <= limit <= 128
                or not state["minute"] <= target <= 1000000):
            raise ValueError("Invalid narrative time or causal event allowance.")

        def move_clock(new_time):
            for due in spec.get("schedule", []):
                if state["minute"] < due["at"] <= new_time:
                    deliver(state, due["effects"])
            state["minute"] = new_time

        if "life" in state:
            life = state["life"]
            next_due = life["queue"][life["cursor"]:life["cursor"] + 1]
            if target == state["minute"] and not (next_due and next_due[0]["at"] <= target):
                raise ValueError("The target minute has already been reached.")
            return world_life.advance(state, target, limit, move_clock)
        if state["minute"] == target:
            raise ValueError("The target minute has already been reached.")
        move_clock(target)
    elif event["kind"] == "choice":
        actor, key = event["actor"], event["choice"]
        offered = choices(spec, state, actor)
        if key not in offered:
            raise ValueError("Recorded choice was unavailable in this state.")
        effects = offered[key]["effects"]
        state["trajectory"][actor].append({"at": state["minute"], "action": key, "label": offered[key]["label"]})
        deliver(state, effects)
    elif event["kind"] == "materialize":
        world_life.materialize(state["life"], event)
    else:
        raise ValueError("Unknown world event kind.")
    return {}


def branch_info(db, run, branch):
    row = db.execute("SELECT * FROM world_branches WHERE run=? AND branch=?", (run, branch)).fetchone()
    if row is None:
        raise ValueError("World or branch unavailable.")
    return row


def replay(db, run, branch, upto=None):
    """Check a branch's full ancestry and derive state from its immutable journal."""
    row = db.execute("SELECT spec,seed FROM world_runs WHERE name=?", (run,)).fetchone()
    if row is None:
        raise ValueError("World unavailable.")
    spec = json.loads(row["spec"])
    seed = records.checksum(records.json_bytes([run, spec]))
    if seed != row["seed"]:
        raise ValueError("World seed digest mismatch.")
    tip = branch_info(db, run, branch)
    limit = tip["head"] if upto is None else upto
    if not (tip["fork_revision"] or 0) <= limit <= tip["head"]:
        raise ValueError("Revision outside the branch.")
    path = []
    seen = set()
    while True:
        if tip["branch"] in seen:
            raise ValueError("Invalid world branch ancestry.")
        seen.add(tip["branch"])
        path.append((tip, limit))
        if tip["parent"] is None:
            break
        limit = tip["fork_revision"]
        tip = branch_info(db, run, tip["parent"])
    state, rev, digest = initial(spec), 0, seed
    for item, limit in reversed(path):
        rows = db.execute("""SELECT revision,body,previous,digest FROM world_events
                             WHERE run=? AND branch=? AND revision<=? ORDER BY revision""",
                          (run, item["branch"], limit))
        for event in rows:
            expected = records.checksum(bytes.fromhex(digest) + event["body"])
            if event["revision"] != rev + 1 or event["previous"] != digest or event["digest"] != expected:
                raise ValueError("World journal chain is inconsistent.")
            apply(state, spec, json.loads(event["body"]))
            rev, digest = event["revision"], expected
        if rev != limit or (limit == item["head"] and digest != item["digest"]):
            raise ValueError("World journal does not match its saved revision.")
    return spec, state, rev, digest


def view(spec, state, actor, fields=None):
    people = state.get("life", {}).get("people", {})
    if actor not in spec["actors"] and actor not in people:
        raise ValueError("Actor unavailable.")
    result = {"actor": actor, "minute": state["minute"], "public": state["public"],
              "profile": spec["actors"].get(actor, {}).get("profile"),
              "knowledge": state["actors"].get(actor, {}), "trajectory": state["trajectory"].get(actor, [])}
    if actor in people:
        result["life"] = world_life.observation(state["life"], actor)
    if fields is None:
        return result
    selected = {}
    for key in fields:
        group, sep, leaf = key.partition(".")
        if sep and group in ("public", "knowledge") and leaf in result[group]:
            selected[key] = result[group][leaf]
        elif group == "life" and leaf in ("location", "goal") and "life" in result:
            selected[key] = result["life"][leaf]
        elif key in ("minute", "profile"):
            selected[key] = result[key]
        else:
            raise ValueError("Field outside the available actor projection.")
    return {"actor": actor, "fields": selected}


def pending(db, run, branch):
    return db.execute("SELECT id,stage FROM world_requests WHERE run=? AND branch=? AND stage<>'settled'",
                      (run, branch)).fetchone()


def ready(db, run, branch):
    open_turn = pending(db, run, branch)
    if open_turn:
        raise ValueError("The branch already has an unsettled actor decision.")


def journal_capacity(db, run):
    events = db.execute("SELECT count(*) FROM world_events WHERE run=?", (run,)).fetchone()[0]
    pending = db.execute("SELECT count(*) FROM world_requests WHERE run=? AND stage<>'settled'", (run,)).fetchone()[0]
    return 512 - events - pending


def append(db, run, branch, expected, event):
    spec, state, rev, prev = replay(db, run, branch)
    if rev != expected:
        raise ValueError("Stale world revision.")
    old_minute = state["minute"]
    detail = apply(state, spec, event)
    if detail.get("paused") and not detail["processed"] and old_minute == state["minute"]:
        return {"run": run, "branch": branch, "revision": rev, "minute": old_minute, "sha256": prev, **detail}
    if event["kind"] != "choice" and journal_capacity(db, run) < 1:
        raise ValueError("World journal capacity is exhausted or reserved for an outstanding decision.")
    body = records.json_bytes(event)
    digest = records.checksum(bytes.fromhex(prev) + body)
    db.execute("INSERT INTO world_events VALUES(?,?,?,?,?,?)", (run, branch, rev + 1, body, prev, digest))
    db.execute("UPDATE world_branches SET head=?,digest=? WHERE run=? AND branch=?", (rev + 1, digest, run, branch))
    return {"run": run, "branch": branch, "revision": rev + 1, "minute": state["minute"], "sha256": digest, **detail}


def get_turn(db, args):
    row = db.execute("SELECT * FROM world_requests WHERE run=? AND id=?", (args.run, args.id)).fetchone()
    if row is None or row["branch"] != args.branch:
        raise ValueError("Unknown request for this branch.")
    return row


def turn(db, args):
    name, branch, id_ = args.run, args.branch, records.nonempty(args.id)
    action = args.world_action
    if action == "request":
        old = db.execute("SELECT * FROM world_requests WHERE run=? AND id=?", (name, id_)).fetchone()
        if old:
            if (old["branch"], old["actor"], old["revision"]) != (branch, args.actor, args.expect):
                raise ValueError("Request ID already binds different world input.")
            if old["stage"] != "prepared":
                return {"id": id_, "stage": old["stage"]}
            return {"stage": "prepared", "packet": json.loads(old["packet"])}
        ready(db, name, branch)
        spec, state, rev, _ = replay(db, name, branch)
        if rev != args.expect:
            raise ValueError("Stale world revision.")
        if args.actor not in spec["actors"]:
            raise ValueError("This person is outside the selected decision roster.")
        actor_view = view(spec, state, args.actor)
        actions = choices(spec, state, args.actor)
        if not actions:
            raise ValueError("This actor has no authored choice.")
        used = db.execute("SELECT count(*) FROM world_requests WHERE run=?", (name,)).fetchone()[0]
        if used >= spec.get("request_limit", 256):
            raise ValueError("World request budget exhausted.")
        if journal_capacity(db, name) < 1:
            raise ValueError("World journal lacks capacity for another decision.")
        packet = {"actor_view": actor_view, "actions": {k: a["label"] for k, a in actions.items()}}
        db.execute("INSERT INTO world_requests(run,id,branch,actor,revision,packet,stage) VALUES(?,?,?,?,?,?,'prepared')",
                   (name, id_, branch, args.actor, rev, records.json_bytes(packet)))
        return {"stage": "prepared", "packet": packet}
    row = get_turn(db, args)
    if action == "dispatching":
        if row["stage"] != "prepared":
            raise ValueError("This request was already marked for dispatch. Inspect its state.")
        db.execute("UPDATE world_requests SET stage='dispatching' WHERE run=? AND id=?", (name, id_))
        return {"id": id_, "stage": "dispatching"}
    if action == "result":
        if row["choice"] is not None:
            if row["choice"] != args.choice:
                raise ValueError("Conflicting recorded actor choice.")
            return {"id": id_, "stage": row["stage"]}
        if row["stage"] != "dispatching" or args.choice not in json.loads(row["packet"])["actions"]:
            raise ValueError("Expected a dispatched request and an offered action key.")
        db.execute("UPDATE world_requests SET choice=?,stage='result-recorded' WHERE run=? AND id=?",
                   (args.choice, name, id_))
        return {"id": id_, "stage": "result-recorded"}
    if row["stage"] == "settled":
        return json.loads(row["receipt"])
    if row["stage"] != "result-recorded":
        raise ValueError("Settlement needs a recorded result. Dispatch uncertainty requires host evidence.")
    receipt = append(db, name, branch, row["revision"], {"kind": "choice", "actor": row["actor"],
                                                          "choice": row["choice"], "request": id_})
    receipt.update(id=id_, stage="settled")
    db.execute("UPDATE world_requests SET stage='settled',receipt=? WHERE run=? AND id=?",
               (records.json_bytes(receipt), name, id_))
    return receipt


def natural(value):
    n = int(value)
    if not 0 <= n <= 2**63-1:
        raise argparse.ArgumentTypeError("Expected nonnegative 64-bit integer.")
    return n


def register(subs):
    parser = subs.add_parser("world", help="advance a local world and select actor-visible material")
    parser.add_argument("--run", required=True)
    parser.add_argument("--branch", default="main")
    sub = parser.add_subparsers(dest="world_action", required=True)
    sub.add_parser("create").add_argument("spec", type=Path)
    sub.add_parser("status")
    sub.add_parser("history", help="owner view of processed life events")
    sub.add_parser("replay").add_argument("--revision", type=natural)
    sub.add_parser("checkpoint").add_argument("name")
    p = sub.add_parser("fork")
    p.add_argument("name")
    p.add_argument("--checkpoint", required=True)
    p = sub.add_parser("advance-time")
    p.add_argument("--target", type=natural, required=True)
    p.add_argument("--expect", type=natural, required=True)
    p.add_argument("--event-limit", type=natural, default=128, help="maximum causal events in this time slice")
    p = sub.add_parser("materialize", help="name a specific encountered member of an aggregate group")
    for field in ("person", "group", "member", "observer", "cause"):
        p.add_argument("--" + field, required=True)
    p.add_argument("--expect", type=natural, required=True)
    for cmd in ("projection", "capture"):
        p = sub.add_parser(cmd)
        p.add_argument("--actor", required=True)
        p.add_argument("--field", action="append", required=cmd == "capture")
        p.add_argument("--revision", type=natural, help="pin a saved branch revision")
        if cmd == "capture":
            p.add_argument("name")
            p.add_argument("--operation", required=True)
            p.add_argument("--parent")
    for cmd in ("request", "dispatching", "result", "settle"):
        p = sub.add_parser(cmd)
        p.add_argument("--id", required=True)
        if cmd == "request":
            p.add_argument("--actor", required=True)
            p.add_argument("--expect", type=natural, required=True)
        if cmd == "result":
            p.add_argument("--choice", required=True)


def writable(args):
    return args.world_action not in ("status", "replay", "projection", "history")


def run(db, args):
    action, name, branch = args.world_action, records.nonempty(args.run), records.nonempty(args.branch)
    if action in ("create", "fork", "advance-time", "materialize", "request", "dispatching"):
        if not records.settings(db)["world_sandbox"]:
            raise ValueError("World Sandbox is switched off.")
    if action == "create":
        if branch != "main":
            raise ValueError("Create a world on main before forking.")
        spec = spec_from(args.spec)
        seed = records.checksum(records.json_bytes([name, spec]))
        db.execute("INSERT INTO world_runs VALUES(?,?,?)", (name, records.json_bytes(spec), seed))
        db.execute("INSERT INTO world_branches VALUES(?,?,NULL,NULL,0,?)", (name, branch, seed))
        return {"run": name, "branch": branch, "revision": 0, "sha256": seed}
    if action in ("request", "dispatching", "result", "settle"):
        return turn(db, args)
    if action == "advance-time":
        ready(db, name, branch)
        event = {"kind": action, "minute": args.target}
        if args.event_limit != 128:
            event["event_limit"] = args.event_limit
        return append(db, name, branch, args.expect, event)
    if action == "materialize":
        ready(db, name, branch)
        _, state, rev, _ = replay(db, name, branch)
        if "life" not in state:
            raise ValueError("Naming requires a populated world.")
        event = {k: records.nonempty(getattr(args, k)) for k in ("group", "member", "person", "observer", "cause")}
        event["kind"] = "materialize"
        if world_life.existing(state["life"], event):
            origin = state["life"]["origins"][args.group, args.member]
            rev = origin.get("identity_revision", rev)
        else:
            event["identity_revision"] = rev + 1
            rev = append(db, name, branch, args.expect, event)["revision"]
        return {"person": args.person, "revision": rev, "origin": {k: event[k] for k in ("group", "member", "observer", "cause")}}
    if action == "fork":
        ready(db, name, branch)
        child = records.nonempty(args.name)
        if db.execute("SELECT count(*) FROM world_branches WHERE run=?", (name,)).fetchone()[0] >= 3:
            raise ValueError("World branch budget exhausted.")
        cp = db.execute("SELECT revision,digest FROM world_checkpoints WHERE run=? AND branch=? AND name=?",
                        (name, branch, args.checkpoint)).fetchone()
        if cp is None:
            raise ValueError("World checkpoint unavailable.")
        _, _, rev, digest = replay(db, name, branch, cp["revision"])
        if digest != cp["digest"]:
            raise ValueError("World checkpoint digest mismatch.")
        db.execute("INSERT INTO world_branches VALUES(?,?,?,?,?,?)", (name, child, branch, rev, rev, digest))
        return {"run": name, "branch": child, "parent": branch, "revision": rev, "sha256": digest}
    spec, state, rev, digest = replay(db, name, branch, getattr(args, "revision", None))
    mark = {"run": name, "branch": branch, "revision": rev, "minute": state["minute"], "sha256": digest}
    if action == "checkpoint":
        cp = records.nonempty(args.name)
        old = db.execute("SELECT revision,digest FROM world_checkpoints WHERE run=? AND branch=? AND name=?",
                         (name, branch, cp)).fetchone()
        if old and (old["revision"], old["digest"]) != (rev, digest):
            raise ValueError("Checkpoint name already pins a different revision.")
        if not old:
            db.execute("INSERT INTO world_checkpoints VALUES(?,?,?,?,?)", (name, branch, cp, rev, digest))
        return {**mark, "checkpoint": cp}
    if action in ("projection", "capture"):
        selected = view(spec, state, args.actor, args.field)
        if action == "projection":
            return selected
        return records.put_record(db, name=args.name, body=records.json_bytes(selected), operation=args.operation,
                                  title=args.name, category="setting", audience="author", authorship="unknown",
                                  origin="World Sandbox", source=records.json_bytes(mark).decode(), parent=args.parent)
    if action == "history":
        return state.get("life", {}).get("history", [])
    if action == "status":
        if "life" in state:
            mark["population"] = world_life.population(state["life"])
        row = pending(db, name, branch)
        return {**mark, "pending": dict(row) if row else None}
    return {**mark, "verified": True}
