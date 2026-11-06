"""Bounded world transitions with actor-scoped observations.

The owner controls this in-memory simulation. Actors receive only observations
and request envelopes. This is a data boundary, not an OS security sandbox or a
replacement for application permissions or content-adoption decisions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
import re
import secrets
from threading import RLock
from typing import Any

from . import _life as life_rules


MAX_BYTES = 4 * 1024 * 1024
CHECKPOINT_SCHEMA = "lotus-world-checkpoint/2"
RECORDING_SCHEMA = "lotus-world-recording/2"
IDENTITY = ("world_id", "branch_id", "actor_id", "request_id", "base_version", "completion_capability")
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class SimulationError(ValueError):
    """Stable error code without echoing private state or caller payloads."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _Refusal(SimulationError):
    pass


def _require(condition: bool, code: str = "invalid_state") -> None:
    if not condition:
        raise SimulationError(code)


def _fields(value: Any, names: set[str], code: str = "invalid_state") -> None:
    _require(type(value) is dict and set(value) == names, code)


def _slug(value: Any) -> bool:
    return type(value) is str and SLUG.fullmatch(value) is not None


def _integer(value: Any, maximum: int = 10**9) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _text(value: Any) -> bool:
    return type(value) is str and 0 < len(value) <= 2000


def _capability(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        _require(len(raw) <= MAX_BYTES, "size_limit")
        return raw
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, SimulationError):
            raise
        raise SimulationError("invalid_json") from None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decode(raw: str) -> Any:
    def unique(pairs):
        result = {}
        for name, value in pairs:
            _require(name not in result, "duplicate_key")
            result[name] = value
        return result

    try:
        _require(type(raw) is str and len(raw.encode("utf-8")) <= MAX_BYTES, "size_limit")
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(SimulationError("invalid_json")))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, SimulationError):
            raise
        raise SimulationError("invalid_json") from None


def _validate_state(state: dict) -> None:
    _fields(state, {"world_id", "branch_id", "lineage", "tick", "version", "locations",
                    "actors", "items", "doors", "facts"} | ({"life"} if type(state) is dict and "life" in state else set()))
    _require(_slug(state["world_id"]) and _slug(state["branch_id"]))
    lineage = state["lineage"]
    _require(type(lineage) is list and len(lineage) <= 32 and all(_slug(x) for x in lineage)
             and len(set(lineage)) == len(lineage) and state["branch_id"] not in lineage)
    _require(_integer(state["tick"]) and state["version"] == state["tick"]
             and _integer(state["version"]))
    places = state["locations"]
    _require(type(places) is list and 1 <= len(places) <= 32 and all(_slug(x) for x in places)
             and len(set(places)) == len(places))
    actors, items = state["actors"], state["items"]
    _require(type(actors) is dict and 1 <= len(actors) <= (life_rules.MAX_NAMED if "life" in state else 32) and all(_slug(x) for x in actors))
    for actor in actors.values():
        _fields(actor, {"location", "coins", "memory"})
        _require(actor["location"] in places and _integer(actor["coins"]))
        _require(type(actor["memory"]) is list and len(actor["memory"]) <= 256)
        for memory in actor["memory"]:
            _fields(memory, {"kind", "text", "source"})
            _require(memory["kind"] in {"belief", "observation"} and _text(memory["text"])
                     and _text(memory["source"]))
    _require(type(items) is dict and len(items) <= 128 and all(_slug(x) for x in items))
    for item in items.values():
        _fields(item, {"location", "owner", "price"})
        _require((item["owner"] is None and item["location"] in places)
                 or (item["owner"] in actors and item["location"] is None))
        _require(item["price"] is None or _integer(item["price"]) and item["price"] > 0)
    _require(type(state["doors"]) is dict and len(state["doors"]) <= 64)
    for name, door in state["doors"].items():
        _fields(door, {"locations", "key", "locked"})
        _require(_slug(name) and type(door["locations"]) is list and len(door["locations"]) == 2
                 and len(set(door["locations"])) == 2 and all(x in places for x in door["locations"])
                 and door["key"] in items and type(door["locked"]) is bool)
    _require(type(state["facts"]) is dict and len(state["facts"]) <= 128)
    for name, fact in state["facts"].items():
        _fields(fact, {"text", "audience"})
        _require(_slug(name) and _text(fact["text"]) and type(fact["audience"]) is list
                 and bool(fact["audience"]) and all(x in actors for x in fact["audience"])
                 and len(set(fact["audience"])) == len(fact["audience"]))

    if "life" in state:
        life_rules.validate(state, _require, _fields, _slug, _integer, _text)


def _validate_data(data: dict) -> None:
    _fields(data, {"state", "events", "pending", "receipts", "budget"})
    _validate_state(data["state"])
    state = data["state"]
    _fields(data["budget"], {"limit", "issued"})
    _require(_integer(data["budget"]["limit"], 256) and data["budget"]["limit"] > 0
             and _integer(data["budget"]["issued"], data["budget"]["limit"]))
    _require(type(data["pending"]) is dict and type(data["receipts"]) is dict
             and not set(data["pending"]).intersection(data["receipts"])
             and len(data["pending"]) + len(data["receipts"]) == data["budget"]["issued"])
    _require(type(data["events"]) is list and len(data["events"]) == state["version"])
    for number, event in enumerate(data["events"], 1):
        _fields(event, {"event_id", "world_id", "branch_id", "actor_id", "request_id",
                        "version", "tick", "action", "audience"})
        _require(event["event_id"] == f"event-{number}" and event["world_id"] == state["world_id"]
                 and event["branch_id"] in [state["branch_id"], *state["lineage"]]
                 and ((event["actor_id"] in state["actors"] and _slug(event["request_id"]))
                      or ("life" in state and event["actor_id"] is None and event["request_id"] is None))
                 and type(event["version"]) is int and event["version"] == event["tick"] == number
                 and type(event["action"]) is dict and type(event["audience"]) is list
                 and bool(event["audience"]) and all(x in state["actors"] for x in event["audience"]))
    for request_id, request in data["pending"].items():
        _fields(request, set(IDENTITY) | {"observation"})
        _require(_slug(request_id) and request["request_id"] == request_id
                 and request["world_id"] == state["world_id"] and request["branch_id"] == state["branch_id"]
                 and request["actor_id"] in state["actors"] and _integer(request["base_version"])
                 and request["base_version"] <= state["version"] and type(request["observation"]) is dict
                 and _capability(request["completion_capability"]))
    for request_id, cached in data["receipts"].items():
        _fields(cached, {"request", "proposal_sha256", "result"})
        _require(_slug(request_id) and cached["request"]["request_id"] == request_id)
        _fields(cached["request"], set(IDENTITY) | {"observation"})
        _require(_capability(cached["request"]["completion_capability"]))
        _fields(cached["result"], {"status", "code", "request_id", "version", "tick", "event_id"})
        result = cached["result"]
        _require(result["request_id"] == request_id and result["status"] in {"accepted", "rejected"}
                 and _integer(result["version"]) and result["version"] == result["tick"] <= state["version"])
        if result["status"] == "accepted":
            _require(0 < result["version"] <= len(data["events"]))
            event = data["events"][result["version"] - 1]
            _require(event["event_id"] == result["event_id"] and event["request_id"] == request_id)
        else:
            _require(result["event_id"] is None)
        digest = cached["proposal_sha256"]
        _require(digest is None and result["code"] == "branch_forked"
                 or type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)


def make_proposal(request: dict, action: dict) -> dict:
    """A decision client receives a request and returns intent, not new facts."""
    _fields(request, set(IDENTITY) | {"observation"}, "invalid_request")
    _require(type(action) is dict, "invalid_action")
    result = {name: deepcopy(request[name]) for name in IDENTITY}
    result["action"] = deepcopy(action)
    _canonical(result)
    return result


class WorldSimulation:
    """One in-process writer with versioned proposals and bounded requests.

    snapshot/checkpoint/recording are trusted-owner interfaces containing private
    data. Never pass them to a character client. A lock serializes mutations of
    this instance; independent instances and filesystem writers are not locked.
    """

    def __init__(self, scenario: dict, *, max_requests: int = 12):
        state = deepcopy(scenario)
        _validate_state(state)
        _require(state["tick"] == 0 and not state["lineage"], "initial_state_required")
        data = {"state": state, "events": [], "pending": {}, "receipts": {},
                "budget": {"limit": max_requests, "issued": 0}}
        self._initialize(data)

    def _initialize(self, seed: dict) -> None:
        _validate_data(seed)
        _require(not seed["pending"], "invalid_seed")
        self._lock = RLock()
        self._data = deepcopy(seed)
        self._seed = deepcopy(seed)
        self._commands: list[dict] = []
        _canonical(seed)

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._data)

    @property
    def budget(self) -> dict:
        with self._lock:
            budget = self._data["budget"]
            return {**budget, "remaining": budget["limit"] - budget["issued"],
                    "in_flight": len(self._data["pending"])}

    def observation(self, actor_id: str) -> dict:
        with self._lock:
            state = self._data["state"]
            _require(_slug(actor_id) and actor_id in state["actors"], "unknown_actor")
            actor = state["actors"][actor_id]
            visible_actors = [name for name, other in state["actors"].items()
                              if other["location"] == actor["location"]]
            result = {"actor_id": actor_id, "actor": actor,
                "actors": sorted(visible_actors),
                "items": {name: item for name, item in state["items"].items()
                          if item["owner"] in visible_actors or item["location"] == actor["location"]},
                "doors": {name: door for name, door in state["doors"].items()
                          if actor["location"] in door["locations"]},
                "facts": {name: {"text": fact["text"]} for name, fact in state["facts"].items()
                          if actor_id in fact["audience"]},
                "events": [event for event in self._data["events"] if actor_id in event["audience"]]}
            if "life" in state:
                result["life"] = life_rules.view(state, actor_id)
            return deepcopy(result)

    def _install(self, data: dict, command: dict) -> None:
        _validate_data(data)
        commands = self._commands + [deepcopy(command)]
        _require(len(commands) + len(data["pending"]) <= 512, "command_limit")
        _canonical({"seed": self._seed, "current": data, "commands": commands})
        self._data, self._commands = data, commands

    def request(self, actor_id: str, request_id: str) -> dict:
        return self._issue_request(actor_id, request_id)

    def _issue_request(self, actor_id: str, request_id: str, capability: str | None = None) -> dict:
        """Only owner-controlled replay supplies captured request entropy."""
        with self._lock:
            _require(_slug(request_id), "invalid_request_id")
            _require(_slug(actor_id) and actor_id in self._data["state"]["actors"], "unknown_actor")
            pending, receipts = self._data["pending"], self._data["receipts"]
            existing = pending.get(request_id) or receipts.get(request_id, {}).get("request")
            if existing is not None:
                _require(existing["actor_id"] == actor_id, "request_id_conflict")
                _require(request_id in pending, "request_closed")
                _require(capability is None or capability == existing["completion_capability"], "invalid_recording")
                return deepcopy(existing)
            _require(self._data["budget"]["issued"] < self._data["budget"]["limit"], "budget_exhausted")
            _require(all(row["actor_id"] != actor_id for row in pending.values()), "actor_pending")
            capability = secrets.token_hex(32) if capability is None else capability
            _require(_capability(capability), "invalid_capability")
            issued = [*pending.values(), *(row["request"] for row in receipts.values())]
            _require(all(row["completion_capability"] != capability for row in issued), "invalid_capability")
            state = self._data["state"]
            request = {"world_id": state["world_id"], "branch_id": state["branch_id"],
                       "actor_id": actor_id, "request_id": request_id, "base_version": state["version"],
                       "completion_capability": capability,
                       "observation": self.observation(actor_id)}
            staged = deepcopy(self._data)
            staged["pending"][request_id] = deepcopy(request)
            staged["budget"]["issued"] += 1
            self._install(staged, {"kind": "request", "actor_id": actor_id, "request_id": request_id,
                                   "completion_capability": capability})
            return deepcopy(request)

    @staticmethod
    def _apply(state: dict, actor_id: str, action: dict, fault) -> list[str]:
        def require(condition, code):
            if not condition:
                raise _Refusal(code)

        schemas = {"wait": {"type"}, "take": {"type", "item"},
                   "unlock": {"type", "door"}, "move": {"type", "to"},
                   "trade": {"type", "item", "seller", "price"},
                   "share": {"type", "fact", "to"}}
        kind = action.get("type")
        require(type(kind) is str and kind in schemas and set(action) == schemas[kind], "invalid_action")
        actor = state["actors"][actor_id]
        audience = sorted(name for name, row in state["actors"].items() if row["location"] == actor["location"])
        if kind == "take":
            require(_slug(action["item"]) and action["item"] in state["items"], "item_unavailable")
            item = state["items"][action["item"]]
            require(item["owner"] is None and item["location"] == actor["location"], "item_unavailable")
            item.update(owner=actor_id, location=None)
        elif kind == "unlock":
            require(_slug(action["door"]) and action["door"] in state["doors"], "door_unavailable")
            door = state["doors"][action["door"]]
            require(actor["location"] in door["locations"] and door["locked"], "door_unavailable")
            require(state["items"][door["key"]]["owner"] == actor_id, "key_required")
            door["locked"] = False
        elif kind == "move":
            require(_slug(action["to"]) and action["to"] in state["locations"]
                    and action["to"] != actor["location"], "invalid_destination")
            require(any(set(door["locations"]) == {actor["location"], action["to"]} and not door["locked"]
                        for door in state["doors"].values()), "route_blocked")
            actor["location"] = action["to"]
            if "life" in state:
                state["life"]["people"][actor_id]["anchor"] = state["life"]["time"]
        elif kind == "trade":
            require(_slug(action["item"]) and action["item"] in state["items"]
                    and _slug(action["seller"]) and action["seller"] in state["actors"]
                    and action["seller"] != actor_id and _integer(action["price"])
                    and action["price"] > 0, "trade_unavailable")
            item, seller = state["items"][action["item"]], state["actors"][action["seller"]]
            require(item["owner"] == action["seller"] and seller["location"] == actor["location"]
                    and item["price"] == action["price"], "trade_unavailable")
            require(actor["coins"] >= action["price"], "insufficient_funds")
            actor["coins"] -= action["price"]
            if fault is not None:
                fault("after_debit")
            seller["coins"] += action["price"]
            item.update(owner=actor_id, price=None)
        elif kind == "share":
            require(_slug(action["fact"]) and action["fact"] in state["facts"]
                    and _slug(action["to"]) and action["to"] in state["actors"]
                    and action["to"] != actor_id, "share_unavailable")
            fact, target = state["facts"][action["fact"]], state["actors"][action["to"]]
            require(actor_id in fact["audience"] and actor["location"] == target["location"]
                    and action["to"] not in fact["audience"], "share_unavailable")
            fact["audience"] = sorted([*fact["audience"], action["to"]])
            target["memory"].append({"kind": "observation", "text": fact["text"],
                                      "source": f"event-{state['version'] + 1}"})
            audience = sorted([actor_id, action["to"]])
        return audience

    def resolve(self, proposal: dict, *, fault=None) -> dict:
        with self._lock:
            _fields(proposal, set(IDENTITY) | {"action"}, "invalid_proposal")
            _canonical(proposal)
            state = self._data["state"]
            _require(proposal["world_id"] == state["world_id"], "foreign_world")
            _require(proposal["branch_id"] == state["branch_id"], "foreign_branch")
            _require(_slug(proposal["request_id"]) and _slug(proposal["actor_id"])
                     and _integer(proposal["base_version"]) and type(proposal["action"]) is dict,
                     "invalid_proposal")
            _require(_capability(proposal["completion_capability"]), "invalid_proposal")
            request_id, proposal_sha = proposal["request_id"], _digest(proposal)
            cached = self._data["receipts"].get(request_id)
            if cached is not None:
                _require(cached["proposal_sha256"] == proposal_sha, "request_id_conflict")
                return deepcopy(cached["result"])
            request = self._data["pending"].get(request_id)
            _require(request is not None, "unknown_request")
            _require(hmac.compare_digest(proposal["completion_capability"], request["completion_capability"]),
                     "request_identity_mismatch")
            _require(all(proposal[name] == request[name] for name in IDENTITY), "request_identity_mismatch")
            staged = deepcopy(self._data)
            current = staged["state"]
            status, code, event_id = "rejected", "stale_version", None
            if proposal["base_version"] == current["version"]:
                action_state = deepcopy(current)
                try:
                    audience = self._apply(action_state, proposal["actor_id"], proposal["action"], fault)
                    action_state["tick"] += 1
                    action_state["version"] += 1
                    _validate_state(action_state)
                except _Refusal as exc:
                    code = exc.code
                else:
                    current = staged["state"] = action_state
                    status, code = "accepted", "committed"
                    event_id = f"event-{current['version']}"
                    staged["events"].append({"event_id": event_id, "world_id": current["world_id"],
                        "branch_id": current["branch_id"], "actor_id": proposal["actor_id"],
                        "request_id": request_id, "version": current["version"], "tick": current["tick"],
                        "action": deepcopy(proposal["action"]), "audience": audience})
            result = {"status": status, "code": code, "request_id": request_id,
                      "version": current["version"], "tick": current["tick"], "event_id": event_id}
            del staged["pending"][request_id]
            staged["receipts"][request_id] = {"request": request, "proposal_sha256": proposal_sha,
                                               "result": deepcopy(result)}
            self._install(staged, {"kind": "resolve", "proposal": proposal, "result": result})
            return deepcopy(result)

    @staticmethod
    def _world_event(data, action, audience):
        state = data["state"]
        state["version"] += 1
        state["tick"] += 1
        event_id = f"event-{state['version']}"
        data["events"].append({"event_id": event_id, "world_id": state["world_id"],
            "branch_id": state["branch_id"], "actor_id": None, "request_id": None,
            "version": state["version"], "tick": state["tick"],
            "action": deepcopy(action), "audience": sorted(audience)})
        return event_id

    def advance_time(self, target: int, *, event_limit: int = 16) -> dict:
        """Advance narrative minutes, preserving every unprocessed causal event."""
        with self._lock:
            state = self._data["state"]
            _require("life" in state, "life_unavailable")
            _require(not self._data["pending"], "pending_request")
            _require(_integer(target, life_rules.MAX_TIME) and target >= state["life"]["time"], "invalid_time")
            _require(_integer(event_limit, life_rules.MAX_EVENTS), "invalid_event_limit")
            staged = deepcopy(self._data)
            state, processed, blocked = staged["state"], [], None
            life = state["life"]
            done = {row["id"] for row in life["history"]}
            due = sorted((e for e in life["queue"] if e["id"] not in done and e["at"] <= target),
                         key=lambda e: (e["at"], e["id"]))
            for event in due:
                if len(processed) == event_limit:
                    blocked = "event_budget"
                    break
                life_rules.update_locations(state, event["at"])
                status, code, audience = life_rules.apply_event(state, event)
                if status == "blocked":
                    blocked = code
                    break
                life["history"].append({k: deepcopy(event[k]) for k in ("id", "at", "cause", "participants")}
                                       | {"status": status, "code": code})
                self._world_event(staged, {"type": "world-event", "cause_id": event["id"],
                                          "change": event["effect"]["type"], "status": status}, audience)
                processed.append(event["id"])
            if blocked is None:
                life_rules.update_locations(state, target)
            result = {"status": "completed" if blocked is None else "paused", "code": blocked,
                      "time": life["time"], "target": target, "processed": processed,
                      "remaining_due": len(due) - len(processed)}
            self._install(staged, {"kind": "advance-time", "target": target,
                                   "event_limit": event_limit, "result": result})
            return deepcopy(result)

    def materialize(self, group_id: str, member_id: str, actor_id: str, *, observer: str, cause_id: str) -> dict:
        """Name one encountered member without duplicating population or prior knowledge."""
        with self._lock:
            state = self._data["state"]
            _require("life" in state, "life_unavailable")
            _require(all(_slug(x) for x in (group_id, member_id, actor_id, observer, cause_id)), "invalid_identity")
            _require(group_id in state["life"]["groups"], "unknown_group")
            group = state["life"]["groups"][group_id]
            if member_id in group["members"]:
                _require(group["members"][member_id] == actor_id, "identity_conflict")
                return {"actor_id": actor_id, "origin": deepcopy(state["life"]["people"][actor_id]["origin"])}
            _require(not self._data["pending"], "pending_request")
            _require(observer in state["actors"] and state["actors"][observer]["location"] == group["location"],
                     "encounter_required")
            _require(any(e["event_id"] == cause_id and observer in e["audience"] for e in self._data["events"]),
                     "visible_cause_required")
            _require(actor_id not in state["actors"], "identity_conflict")
            _require(len(state["actors"]) < life_rules.MAX_NAMED and group["count"] > 0, "population_limit")
            staged = deepcopy(self._data)
            state = staged["state"]
            group = state["life"]["groups"][group_id]
            origin = {"group_id": group_id, "member_id": member_id, "time": state["life"]["time"], "cause": cause_id}
            state["actors"][actor_id] = {"location": group["location"], "coins": 0, "memory": []}
            state["life"]["people"][actor_id] = {"goal": group["role"], "schedule": [],
                "anchor": state["life"]["time"], "relations": {observer: "Met during " + cause_id}, "origin": origin}
            group["members"][member_id] = actor_id
            group["count"] -= 1
            self._world_event(staged, {"type": "encounter", "actor_id": actor_id, "cause_id": cause_id}, [observer, actor_id])
            result = {"actor_id": actor_id, "origin": origin}
            self._install(staged, {"kind": "materialize", "group_id": group_id, "member_id": member_id,
                                   "actor_id": actor_id, "observer": observer, "cause_id": cause_id, "result": result})
            return deepcopy(result)

    def fork(self, new_branch_id: str) -> WorldSimulation:
        with self._lock:
            current = self._data["state"]
            _require(_slug(new_branch_id) and new_branch_id not in [current["branch_id"], *current["lineage"]],
                     "invalid_branch")
            data = deepcopy(self._data)
            data["state"]["lineage"].append(current["branch_id"])
            data["state"]["branch_id"] = new_branch_id
            for request_id, request in data["pending"].items():
                data["receipts"][request_id] = {"request": request, "proposal_sha256": None,
                    "result": {"status": "rejected", "code": "branch_forked", "request_id": request_id,
                               "version": current["version"], "tick": current["tick"], "event_id": None}}
            data["pending"] = {}
            child = object.__new__(type(self))
            child._initialize(data)
            return child

    def recording(self) -> dict:
        with self._lock:
            return deepcopy({"schema": RECORDING_SCHEMA, "seed": self._seed,
                             "commands": self._commands, "final_sha256": _digest(self._data)})

    @classmethod
    def replay(cls, recording: dict) -> WorldSimulation:
        try:
            _canonical(recording)
            _fields(recording, {"schema", "seed", "commands", "final_sha256"}, "invalid_recording")
            _require(recording["schema"] == RECORDING_SCHEMA and type(recording["commands"]) is list
                     and len(recording["commands"]) <= 512, "invalid_recording")
            instance = object.__new__(cls)
            instance._initialize(recording["seed"])
            for command in recording["commands"]:
                _require(type(command) is dict, "invalid_recording")
                if command.get("kind") == "request":
                    _fields(command, {"kind", "actor_id", "request_id", "completion_capability"}, "invalid_recording")
                    instance._issue_request(command["actor_id"], command["request_id"], command["completion_capability"])
                elif command.get("kind") == "resolve":
                    _fields(command, {"kind", "proposal", "result"}, "invalid_recording")
                    _require(instance.resolve(command["proposal"]) == command["result"], "replay_mismatch")
                elif command.get("kind") == "advance-time":
                    _fields(command, {"kind", "target", "event_limit", "result"}, "invalid_recording")
                    _require(instance.advance_time(command["target"], event_limit=command["event_limit"]) == command["result"],
                             "replay_mismatch")
                elif command.get("kind") == "materialize":
                    _fields(command, {"kind", "group_id", "member_id", "actor_id", "observer", "cause_id", "result"},
                            "invalid_recording")
                    _require(instance.materialize(command["group_id"], command["member_id"], command["actor_id"],
                                                  observer=command["observer"], cause_id=command["cause_id"]) == command["result"],
                             "replay_mismatch")
                else:
                    raise SimulationError("invalid_recording")
            _require(_digest(instance._data) == recording["final_sha256"], "replay_mismatch")
            _require(instance._commands == recording["commands"], "replay_mismatch")
            return instance
        except (KeyError, TypeError, IndexError, RecursionError):
            raise SimulationError("invalid_recording") from None

    def checkpoint(self) -> str:
        with self._lock:
            payload = {"recording": self.recording(), "current": self._data}
            return _canonical({"schema": CHECKPOINT_SCHEMA, "payload": payload,
                               "sha256": _digest(payload)}).decode("utf-8")

    @classmethod
    def from_checkpoint(cls, raw: str) -> WorldSimulation:
        try:
            checkpoint = _decode(raw)
            _fields(checkpoint, {"schema", "payload", "sha256"}, "invalid_checkpoint")
            _require(checkpoint["schema"] == CHECKPOINT_SCHEMA, "unsupported_checkpoint")
            payload = checkpoint["payload"]
            _fields(payload, {"recording", "current"}, "invalid_checkpoint")
            _require(_digest(payload) == checkpoint["sha256"], "checkpoint_digest")
            instance = cls.replay(payload["recording"])
            _require(instance.snapshot() == payload["current"], "checkpoint_mismatch")
            return instance
        except (KeyError, TypeError, IndexError, RecursionError):
            raise SimulationError("invalid_checkpoint") from None
