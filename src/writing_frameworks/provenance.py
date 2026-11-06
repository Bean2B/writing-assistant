"""Versioned producer relationships and explicit output-capture boundaries.

This companion retains the 0.1.0 packet/collection shapes and prior valid
packets. It does not store content, resolve references, dispatch a model or
authenticate a host. Explicit review phase support is documented in docs/interface.md.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re

from . import __version__
from .core.contracts import (canonical, digest, fields, reference, require,
                             text, utf8, MAX_MATERIALS)
from .core.selection import phase_for, select
from .producer import collect as collect_v1, prepare as prepare_v1, validate_packet

REQUEST_CONTRACT = "writing-producer-request"
ARTIFACT_CONTRACT = "writing-producer-artifact"
VERSION = 1
SOURCE_KINDS = ("user-supplied", "producer-output", "record-version",
                "sandbox-projection", "synthetic", "unknown")
ROLES = ("request-material", "prior-prose", "current-draft", "feedback", "scene-projection")
ARTIFACT_KINDS = {"concept": "idea", "draft": "draft", "plan-scene": "planning",
                  "reader-review": "feedback", "continuity-review": "feedback", "revise": "revision"}
CAPTURE_KINDS = ("supplied-bytes", "host-payload-bytes", "host-text")
COMPLETENESS = ("complete", "partial", "unknown")
ASSURANCE = "caller-reported-not-authenticated"


def _contract(value, identity):
    fields(value, ("id", "version"))
    require(value["id"] == identity and type(value["version"]) is int and value["version"] == VERSION,
            "unsupported_version", "Unsupported producer companion contract.")


def _sha(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "invalid_reference", "An exact lowercase SHA-256 is required.")


def _sources(value, selected, phase):
    require(type(value) is list and len(value) <= MAX_MATERIALS,
            "invalid_sources", "A bounded ordered source list is required.")
    require(type(selected) is list and len(value) == len(selected),
            "invalid_sources", "Every selected input requires one ordered source declaration.")
    result = []
    for row, expected in zip(value, selected):
        fields(row, ("role", "kind", "reference"))
        require(row["role"] in ROLES and row["kind"] in SOURCE_KINDS,
                "invalid_sources", "Unsupported source role or kind.")
        ref = reference(row["reference"])
        require(ref == reference(expected), "invalid_relation", "Source references differ from selected inputs.")
        result.append({"role": row["role"], "kind": row["kind"], "reference": ref})
    require(len({row["reference"]["uri"] for row in result}) == len(result),
            "invalid_relation", "Duplicate selected source URIs are ambiguous.")
    drafts = [row for row in result if row["role"] == "current-draft"]
    require(len(drafts) <= 1, "invalid_relation", "Only one exact current draft may be selected.")
    if phase in ("reader-review", "continuity-review", "revise"):
        require(len(drafts) == 1, "invalid_relation", "This phase requires one explicitly selected current draft.")
    if phase == "revise":
        require(any(row["role"] == "feedback" for row in result),
                "invalid_relation", "Revision requires explicitly selected feedback.")
    return result


def prepare(request, *, sources, resolver=None):
    """Bind source relationships before method loading or selected input reads."""
    fields(request, ("schema_version", "request_id", "request", "phase", "context", "materials"), ("selection",))
    selected = _sources(sources, request["materials"], request["phase"])
    packet = prepare_v1(request, resolver=resolver)
    if packet["status"] == "new-context-required":
        return packet
    result = {"contract": {"id": REQUEST_CONTRACT, "version": VERSION}, "packet": packet, "sources": selected}
    result["request_sha256"] = digest(canonical(result))
    return result


def validate_prepared(value):
    fields(value, ("contract", "packet", "sources", "request_sha256"))
    _contract(value["contract"], REQUEST_CONTRACT)
    _sha(value["request_sha256"])
    unsigned = dict(value); unsigned.pop("request_sha256")
    require(digest(canonical(unsigned)) == value["request_sha256"],
            "changed_packet", "Prepared source relationships changed.")
    packet = validate_packet(value["packet"])
    _sources(value["sources"], [item["reference"] for item in packet["materials"]], packet["phase"])
    return value


@dataclass(frozen=True)
class CapturedOutput:
    original: bytes | str
    bytes_to_store: bytes
    descriptor: dict


def capture_output(original, *, kind, completeness="unknown"):
    """Keep the supplied value; UTF-8 encode exposed text without normalization."""
    require(kind in CAPTURE_KINDS and completeness in COMPLETENESS,
            "invalid_capture", "Unsupported output capture boundary or completeness.")
    if kind == "host-text":
        require(type(original) is str, "invalid_capture", "Host text capture requires the exposed string.")
        raw = utf8(original)
        encoding, transport = "utf-8", False
    else:
        require(type(original) is bytes, "invalid_capture", "Byte capture requires the supplied payload bytes.")
        raw = original
        encoding, transport = None, None
    descriptor = {"kind": kind, "storage_encoding": encoding, "transport_bytes_available": transport,
                  "completeness": completeness, "assurance": ASSURANCE}
    return CapturedOutput(original=original, bytes_to_store=raw, descriptor=descriptor)


@dataclass(frozen=True)
class ProducedArtifact:
    capture: CapturedOutput
    envelope: dict


def collect(prepared, captured, *, output_uri, origin, source_kind="unknown", authorship="unknown"):
    """Describe supplied output; create no record, saved file or model receipt."""
    validate_prepared(prepared)
    require(type(captured) is CapturedOutput, "invalid_capture", "An explicit output capture is required.")
    fields(captured.descriptor, ("kind", "storage_encoding", "transport_bytes_available", "completeness", "assurance"))
    checked = capture_output(captured.original, kind=captured.descriptor["kind"],
                             completeness=captured.descriptor["completeness"])
    require(captured.descriptor == checked.descriptor and type(captured.bytes_to_store) is bytes
            and captured.bytes_to_store == checked.bytes_to_store,
            "invalid_capture", "Captured content differs from its declared boundary.")
    packet = prepared["packet"]
    parent = next((row["reference"] for row in prepared["sources"] if row["role"] == "current-draft"), None)
    original = collect_v1(packet, captured.bytes_to_store, output_uri=output_uri, origin=origin,
                          parent=parent if packet["phase"] == "revise" else None)
    envelope = {"contract": {"id": ARTIFACT_CONTRACT, "version": VERSION},
                "request_sha256": prepared["request_sha256"], "artifact_kind": ARTIFACT_KINDS[packet["phase"]],
                "producer_output": original.envelope, "sources": deepcopy(prepared["sources"]),
                "capture": dict(captured.descriptor), "source_kind": source_kind,
                "authorship": {"kind": authorship, "assurance": ASSURANCE}}
    validate_artifact(envelope, prepared=prepared)
    return ProducedArtifact(capture=captured, envelope=envelope)


def validate_artifact(value, *, prepared=None):
    """Validate transport metadata; never resolve content or grant access."""
    fields(value, ("contract", "request_sha256", "artifact_kind", "producer_output", "sources", "capture", "source_kind", "authorship"))
    _contract(value["contract"], ARTIFACT_CONTRACT)
    _sha(value["request_sha256"])
    out = value["producer_output"]
    fields(out, ("schema_version", "producer", "component_version", "request_id", "packet_sha256",
                 "selection", "phase", "method_version", "inputs", "output", "byte_length", "parent",
                 "origin", "origin_assurance", "disposition"))
    require(type(out["schema_version"]) is int and out["schema_version"] == 1
            and out["producer"] == "lotus-writing-producer" and out["component_version"] == __version__,
            "unsupported_version", "Unsupported nested producer output.")
    choice = select(out["selection"]); phase = phase_for(choice["mode"], out["phase"])
    require((choice["mode"] == "none" and out["method_version"] is None) or
            (choice["mode"] == "lotus" and type(out["method_version"]) is int and out["method_version"] == 1),
            "unsupported_version", "Unsupported selected method version.")
    require(text(out["request_id"]) and len(out["request_id"]) <= 256,
            "invalid_contract", "A bounded producer request ID is required.")
    utf8(out["request_id"]); _sha(out["packet_sha256"])
    reference(out["output"])
    require(type(out["byte_length"]) is int and out["byte_length"] >= 0,
            "invalid_contract", "Original output byte length is required.")
    sources = _sources(value["sources"], out["inputs"], phase)
    parent = next((row["reference"] for row in sources if row["role"] == "current-draft"), None)
    require(out["parent"] == (parent if phase == "revise" else None)
            and value["artifact_kind"] == ARTIFACT_KINDS[phase],
            "invalid_relation", "Artifact relations differ from the selected phase and inputs.")
    origin = out["origin"]; fields(origin, ("host", "execution_ref", "status", "evidence_kind"))
    require(origin["host"] == "codex" and origin["status"] in ("completed", "failed", "cancelled", "unknown")
            and origin["evidence_kind"] in ("synthetic", "supplied-output", "host-observation")
            and (origin["execution_ref"] is None or (text(origin["execution_ref"]) and len(origin["execution_ref"]) <= 2048)),
            "invalid_origin", "Unsupported caller-reported origin.")
    if origin["execution_ref"] is not None:
        utf8(origin["execution_ref"])
    require(out["origin_assurance"] == ASSURANCE and out["disposition"] == "unadopted-producer-output",
            "invalid_contract", "Origin assurance and unadopted disposition must be retained.")
    capture = value["capture"]
    fields(capture, ("kind", "storage_encoding", "transport_bytes_available", "completeness", "assurance"))
    require(capture["kind"] in CAPTURE_KINDS and capture["completeness"] in COMPLETENESS
            and capture["assurance"] == ASSURANCE,
            "invalid_capture", "Unsupported output capture descriptor.")
    require((capture["kind"] == "host-text" and capture["storage_encoding"] == "utf-8"
             and capture["transport_bytes_available"] is False) or
            (capture["kind"] != "host-text" and capture["storage_encoding"] is None
             and capture["transport_bytes_available"] is None),
            "invalid_capture", "Capture descriptor overstates its original byte boundary.")
    require(value["source_kind"] in SOURCE_KINDS, "invalid_sources", "Unsupported output source kind.")
    fields(value["authorship"], ("kind", "assurance"))
    require(value["authorship"]["kind"] in ("user", "agent", "mixed", "unknown")
            and value["authorship"]["assurance"] == ASSURANCE,
            "invalid_authorship", "Unsupported caller-reported authorship.")
    if prepared is not None:
        validate_prepared(prepared)
        packet = prepared["packet"]
        require(value["request_sha256"] == prepared["request_sha256"] and value["sources"] == prepared["sources"]
                and all(out[name] == packet[name] for name in ("request_id", "packet_sha256", "selection", "phase", "method_version")),
                "changed_packet", "Artifact does not bind the supplied prepared request.")
    canonical(value)
    return value
