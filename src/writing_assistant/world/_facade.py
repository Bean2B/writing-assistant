"""Bounded owner-facing sandbox advancement with caller-supplied decisions.

Importing this module starts nothing. The caller owns the open RunStore and any
external execution; cooperative pauses do not establish external stop evidence.
"""
from __future__ import annotations

import hashlib
import re

from ._continuity import ContinuityError, RunStore, canonical, slug
from ._simulation import SimulationError, WorldSimulation


class SandboxError(ValueError):
    """A facade contract refusal without private actor or owner data."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise SandboxError(code)


def _known(snapshot):
    if any(job["stage"] == "dispatching" for branch in snapshot["branches"].values()
           for job in branch["jobs"].values()):
        raise ContinuityError("uncertain_request")


def _stop(predicate):
    if predicate is None:
        return False
    value = predicate()
    _require(type(value) is bool, "invalid_stop_result")
    return value


def _selection(purpose, selection):
    _require(type(purpose) is str and purpose in {"actor-projection", "world-projection"},
             "invalid_projection_purpose")
    if purpose == "actor-projection":
        _require(selection is None, "invalid_projection_selection")
        return None
    _require(type(selection) is list and bool(selection), "invalid_projection_selection")
    paths = {}
    for path in selection:
        _require(type(path) is list and bool(path), "invalid_projection_selection")
        for part in path:
            _require((type(part) is int and part >= 0) or
                     (type(part) is str and part not in {"", ".", ".."}
                      and not any(mark in part for mark in ("*", "/", "\\"))),
                     "invalid_projection_selection")
        try:
            key = canonical(path)
        except ContinuityError:
            raise SandboxError("invalid_projection_selection") from None
        _require(key not in paths, "invalid_projection_selection")
        paths[key] = list(path)
    return [paths[key] for key in sorted(paths)]


def _selected(observation, selection):
    entries = []
    for path in selection:
        value = observation
        for part in path:
            if type(value) is dict and type(part) is str and part in value:
                value = value[part]
            elif type(value) is list and type(part) is int and 0 <= part < len(value):
                value = value[part]
            else:
                raise SandboxError("invalid_projection_selection")
        _require(value is None or type(value) in {str, bool, int, float},
                 "invalid_projection_selection")
        entries.append({"path": path, "value": value})
    return entries


def projection(owner, *, actor_id, branch_id="main", purpose="actor-projection", selection=None):
    """Return canonical permitted bytes and their closed material reference.

    Writer selections are explicit lists of scalar-leaf paths rooted in this
    actor's observation. Caller authority and disclosure approval remain external.
    """
    _require(isinstance(owner, RunStore), "invalid_owner")
    _require(slug(actor_id) and slug(branch_id), "invalid_projection_scope")
    selection = _selection(purpose, selection)
    snapshot = owner.snapshot()
    try:
        branch = snapshot["branches"][branch_id]
        view = owner.actor_view(actor_id, branch_id)
        state = WorldSimulation.from_checkpoint(branch["checkpoint"]).snapshot()["state"]
    except KeyError:
        raise SandboxError("projection_unavailable") from None
    except ContinuityError as exc:
        if exc.code != "unknown_actor":
            raise
        raise SandboxError("projection_unavailable") from None
    except SimulationError:
        raise SandboxError("projection_unavailable") from None
    if selection is not None:
        view = _selected(view["observation"], selection)
    body = canonical({"schema_version": "lotus-sandbox-projection/1",
                      "run_id": snapshot["run_id"], "world_id": state["world_id"],
                      "branch_id": branch_id, "world_version": state["version"],
                      "actor_id": actor_id, "purpose": purpose,
                      "selection": selection, "view": view})
    sha256 = hashlib.sha256(body).hexdigest()
    return {"body": body, "reference": {"uri": "lotus-sandbox-projection:1:" + sha256,
                                        "sha256": sha256, "purpose": purpose}}


def resolve_projection(owner, reference, *, actor_id, branch_id="main",
                       purpose="actor-projection", selection=None):
    """Resolve only an exact current reference under independently supplied scope."""
    _require(isinstance(owner, RunStore), "invalid_owner")
    _require(slug(actor_id) and slug(branch_id), "invalid_projection_scope")
    selection = _selection(purpose, selection)
    _require(type(reference) is dict and set(reference) == {"uri", "sha256", "purpose"},
             "invalid_projection_reference")
    _require(type(reference["uri"]) is str and type(reference["sha256"]) is str
             and re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]) is not None
             and reference["uri"] == "lotus-sandbox-projection:1:" + reference["sha256"]
             and type(reference["purpose"]) is str
             and reference["purpose"] in {"actor-projection", "world-projection"},
             "invalid_projection_reference")
    current = projection(owner, actor_id=actor_id, branch_id=branch_id,
                         purpose=purpose, selection=selection)
    _require(reference == current["reference"], "stale_projection_reference")
    return current["body"]


def _settlement_target(snapshot, request_id, branch_id):
    _known(snapshot)
    _require(slug(request_id) and slug(branch_id), "invalid_settlement_identity")
    branch = snapshot["branches"].get(branch_id)
    _require(branch is not None and request_id in branch["jobs"], "settlement_unavailable")
    job = branch["jobs"][request_id]
    _require(job["stage"] in {"result-recorded", "resolved"}, "settlement_not_ready")
    return job


def settle(owner, *, request_id, branch_id="main"):
    """Finish an existing durable result or return its original resolved receipt.

    This operation is available while generation is off and never prepares a
    request, invokes a client or allocates a slot. Any uncertain branch blocks it.
    """
    _require(isinstance(owner, RunStore), "invalid_owner")
    snapshot = owner.snapshot()
    _settlement_target(snapshot, request_id, branch_id)
    # Recheck under the caller's existing owner lock immediately before dispatch.
    snapshot = owner.snapshot()
    job = _settlement_target(snapshot, request_id, branch_id)
    receipt = owner.dispatch(request_id, branch_id)
    return {"run_id": snapshot["run_id"], **job["payload"]["identity"],
            "status": receipt["status"], "code": receipt["code"],
            "version": receipt["version"], "event_id": receipt["event_id"]}


def advance_time(owner, *, target, event_limit=16, branch_id="main", enabled=True,
                 stop_requested=None):
    """Explicit owner-only narrative time; no model dispatch or background timer."""
    _require(type(enabled) is bool, "invalid_enabled")
    _require(enabled, "sandbox_disabled")
    _require(isinstance(owner, RunStore), "invalid_owner")
    _require(stop_requested is None or callable(stop_requested), "invalid_stop_predicate")
    _known(owner.snapshot())
    if _stop(stop_requested):
        return {"scope": "owner-progress", "status": "paused", "code": "stop_requested"}
    return {"scope": "owner-progress", **owner.advance_time(target, event_limit=event_limit,
                                                           branch_id=branch_id)}


def advance(owner, *, decision_client, enabled=True, steps=1, stop_requested=None):
    """Advance the existing main schedule by at most ``steps`` saved decisions.

    ``decision_client`` must accept the original capless JSON bytes and return an
    action dictionary. It is never discovered, replaced by a fake, or called for
    saved result-recorded/completed work. Errors propagate; uncertain work is not
    retried. The result is owner-only progress, not an actor projection or a claim
    that an external execution is stopped. Inspect actors with owner.actor_view.
    """
    _require(type(enabled) is bool, "invalid_enabled")
    _require(enabled, "sandbox_disabled")
    _require(callable(decision_client), "decision_client_required")
    _require(type(steps) is int and 1 <= steps <= 16, "invalid_steps")
    _require(stop_requested is None or callable(stop_requested), "invalid_stop_predicate")
    _require(isinstance(owner, RunStore), "invalid_owner")

    snapshot = owner.snapshot()
    _known(snapshot)
    receipts = []
    stopped = False
    for _ in range(steps):
        snapshot = owner.snapshot()
        _known(snapshot)
        branch = snapshot["branches"]["main"]
        turn = branch["cursor"]
        if turn == snapshot["config"]["turn_limit"]:
            break
        if _stop(stop_requested):
            stopped = True
            break
        request_id = "turn-" + str(turn).zfill(2)
        actor = snapshot["config"]["actor_order"][turn % len(snapshot["config"]["actor_order"])]
        if request_id not in branch["jobs"]:
            payload = owner.prepare(actor, request_id, fixture_turn=turn)
        else:
            job = branch["jobs"][request_id]
            if job["fixture_turn"] != turn:
                raise ContinuityError("turn_conflict")
            payload = job["payload"]
        # A pause here preserves the exact prepared identity and allocated slot.
        if _stop(stop_requested):
            stopped = True
            break
        # Once the callable returns, dispatch saves its action and resolves before
        # another stop poll. Do not discard a returned action because of a pause.
        receipt = owner.dispatch(request_id, client=decision_client)
        receipts.append({"run_id": snapshot["run_id"], **payload["identity"],
                         "status": receipt["status"], "code": receipt["code"],
                         "version": receipt["version"], "event_id": receipt["event_id"]})
        if _stop(stop_requested):
            stopped = True
            break

    snapshot = owner.snapshot()
    branch = snapshot["branches"]["main"]
    return {"scope": "owner-progress", "run_id": snapshot["run_id"], "branch_id": "main",
            "status": "completed" if branch["cursor"] == snapshot["config"]["turn_limit"] else "paused",
            "stop_requested": stopped, "completed_steps": branch["cursor"],
            "planned_steps": snapshot["config"]["turn_limit"], "advanced_steps": len(receipts),
            "receipts": receipts}
