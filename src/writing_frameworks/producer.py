"""Explicit instruction preparation and byte-preserving producer envelopes.

There is no backend, scheduler, record store or implied content adoption.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib

from . import __version__
from .core.contracts import (ContractError, MAX_BYTES, MAX_MATERIALS, MAX_TOTAL_BYTES,
                             bind, canonical, digest, fields, materials, reference,
                             require, text, utf8)
from .core.selection import phase_for, select

REVIEW_INSTRUCTIONS = {
    "reader-review": (
        "Independently describe the reading experience supported by the selected prose. "
        "Use textual evidence and distinguish uncertainty from a demonstrated problem. "
        "Do not infer an author's intended effect, hidden answer or future outcome. "
        "Return feedback on the exact selected draft; do not rewrite or adopt it."
    ),
    "continuity-review": (
        "Check the exact selected draft against only the permitted prior prose and current-scene projection. "
        "Trace knowledge, chronology, space, bodily costs and causal consequences. "
        "Distinguish established events, beliefs, proposals and unknowns. "
        "Return evidence-bound feedback; do not rewrite, adopt prose or update world facts."
    ),
}


def context_declaration(value):
    fields(value, ("id", "fresh", "frameworks_seen"))
    require(text(value["id"]) and len(value["id"]) <= 256 and type(value["fresh"]) is bool,
            "invalid_context", "A bounded caller context declaration is required.")
    utf8(value["id"])
    seen = value["frameworks_seen"]
    require(type(seen) is list and len(seen) <= 32
            and all(text(item) and len(item) <= 128 for item in seen)
            and len(set(seen)) == len(seen), "invalid_context", "Invalid context exposure declaration.")
    for item in seen:
        utf8(item)
    return {"id": value["id"], "fresh": value["fresh"], "frameworks_seen": list(seen)}


def _instructions(mode, phase):
    if mode == "none":
        return []
    if phase in REVIEW_INSTRUCTIONS:
        # Reviewers receive their perspective, not the author's writing method.
        return [REVIEW_INSTRUCTIONS[phase]]
    try:
        adapter = importlib.import_module("writing_frameworks.methods.lotus")
        instruction = adapter.instructions(phase)
    except (ImportError, OSError, AttributeError, KeyError) as error:
        raise ContractError("component_unavailable", "The selected framework component could not be loaded.") from error
    require(text(instruction), "component_unavailable", "The selected framework returned no instructions.")
    return [instruction]


def prepare(request, *, resolver=None):
    """Prepare only selected instructions; never dispatch a model or run reviews."""
    fields(request, ("schema_version", "request_id", "request", "phase", "context", "materials"),
           ("selection",))
    require(type(request["schema_version"]) is int and request["schema_version"] == 1,
            "unsupported_version", "Unsupported writing request version.")
    require(text(request["request_id"]) and len(request["request_id"]) <= 256
            and type(request["request"]) is str and len(utf8(request["request"])) <= MAX_BYTES,
            "invalid_request", "A bounded request ID and UTF-8 request are required.")
    utf8(request["request_id"])
    chosen = select(request["selection"]) if "selection" in request else select()
    phase = phase_for(chosen["mode"], request["phase"])
    ctx = context_declaration(request["context"])
    # Refuse before loading any optional implementation or resolving content.
    if (chosen["mode"] == "none" or phase in REVIEW_INSTRUCTIONS) and (not ctx["fresh"] or ctx["frameworks_seen"]):
        return {"schema_version": 1, "status": "new-context-required", "selection": chosen,
                "request_id": request["request_id"], "instructions": [],
                "reason": "Start a clean host conversation/context for the selected phase. Configuration changes do not erase prior instructions.",
                "assurance": "Caller declaration only; hidden host context is not authenticated."}
    visible = materials(request["materials"], resolver)
    packet = {"schema_version": 1, "component_version": __version__, "status": "ready",
              "request_id": request["request_id"], "selection": chosen, "phase": phase,
              "method_version": 1 if chosen["mode"] == "lotus" else None,
              "context": ctx, "context_assurance": "caller-declared-not-host-authenticated",
              "request": request["request"], "materials": visible,
              "instructions": _instructions(chosen["mode"], phase)}
    packet["packet_sha256"] = digest(canonical(packet))
    return packet


def validate_packet(packet):
    fields(packet, ("schema_version", "component_version", "status", "request_id", "selection",
                   "phase", "method_version", "context", "context_assurance", "request", "materials", "instructions", "packet_sha256"))
    require(type(packet["schema_version"]) is int and packet["schema_version"] == 1
            and packet["component_version"] == __version__ and packet["status"] == "ready",
            "unsupported_version", "A ready packet from this component version is required.")
    raw = dict(packet)
    expected = raw.pop("packet_sha256")
    require(digest(canonical(raw)) == expected, "changed_packet", "Prepared packet bytes changed.")
    chosen = select(packet["selection"])
    phase = phase_for(chosen["mode"], packet["phase"])
    require((chosen["mode"] == "none" and packet["method_version"] is None) or
            (chosen["mode"] == "lotus" and type(packet["method_version"]) is int and packet["method_version"] == 1),
            "unsupported_version", "Unsupported method version.")
    ctx = context_declaration(packet["context"])
    require(chosen["mode"] != "none" or (ctx["fresh"] and not ctx["frameworks_seen"]),
            "context_transition_required", "Direct mode requires a clean declared context.")
    require(packet["context_assurance"] == "caller-declared-not-host-authenticated"
            and text(packet["request_id"]) and len(packet["request_id"]) <= 256
            and type(packet["request"]) is str and len(utf8(packet["request"])) <= MAX_BYTES,
            "invalid_packet", "Invalid prepared request.")
    require(type(packet["materials"]) is list and len(packet["materials"]) <= MAX_MATERIALS,
            "input_limit", "Too many selected materials.")
    total = 0
    for item in packet["materials"]:
        fields(item, ("reference", "text"))
        ref = reference(item["reference"])
        require(type(item["text"]) is str, "invalid_material", "Material text is required.")
        body = utf8(item["text"])
        total += len(body)
        require(len(body) <= MAX_BYTES and total <= MAX_TOTAL_BYTES,
                "input_limit", "Selected material exceeds the byte budget.")
        require(digest(body) == ref["sha256"], "changed_reference", "Material bytes changed.")
    require(type(packet["instructions"]) is list and
            ((chosen["mode"] == "none" and packet["instructions"] == []) or
             (chosen["mode"] == "lotus" and len(packet["instructions"]) == 1 and text(packet["instructions"][0]))),
            "changed_instructions", "Prepared instructions differ from the selected method contract.")
    # Collection binds the supplied historical packet, not today's method files.
    # Its digest is an integrity binding and never authenticates its origin.
    return packet


@dataclass(frozen=True)
class CollectedOutput:
    original: bytes
    envelope: dict


def collect(packet, original, *, output_uri, origin, parent=None):
    """Return original bytes and an exact reference, with no persistence or retry."""
    validate_packet(packet)
    fields(origin, ("host", "execution_ref", "status", "evidence_kind"))
    require(origin["host"] == "codex" and (origin["execution_ref"] is None or
            (text(origin["execution_ref"]) and len(origin["execution_ref"]) <= 2048))
            and origin["evidence_kind"] in ("synthetic", "supplied-output", "host-observation")
            and origin["status"] in ("completed", "failed", "cancelled", "unknown"),
            "invalid_origin", "A supported caller-reported completion observation is required.")
    if origin["execution_ref"] is not None:
        utf8(origin["execution_ref"])
    output = bind(output_uri, original)
    parent = None if parent is None else reference(parent)
    envelope = {"schema_version": 1, "producer": "lotus-writing-producer", "component_version": __version__,
                "request_id": packet["request_id"], "packet_sha256": packet["packet_sha256"],
                "selection": dict(packet["selection"]), "phase": packet["phase"],
                "method_version": packet["method_version"],
                "inputs": [dict(item["reference"]) for item in packet["materials"]],
                "output": output, "byte_length": len(original), "parent": parent,
                "origin": dict(origin), "origin_assurance": "caller-reported-not-authenticated",
                "disposition": "unadopted-producer-output"}
    return CollectedOutput(original=original, envelope=envelope)
