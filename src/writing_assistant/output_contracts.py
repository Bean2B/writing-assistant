"""Fixed core output fields and checks; not a general JSON Schema evaluator."""

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import math
import re

from .core.errors import AssistantError


@dataclass(frozen=True)
class Field:
    schema: dict
    accepts: object


def _string(*, pattern=None, maximum=4096):
    schema = {"type": "string"}
    if maximum is not None:
        schema["maxLength"] = maximum
    if pattern:
        schema["pattern"] = pattern
    return Field(schema, lambda v: type(v) is str and (maximum is None or len(v) <= maximum)
                 and (pattern is None or re.fullmatch(pattern, v) is not None))


def _enum(*values):
    return Field({"enum": list(values)}, lambda v: any(type(v) is type(x) and v == x for x in values))


def _nullable(field):
    return Field({"anyOf": [field.schema, {"type": "null"}]}, lambda v: v is None or field.accepts(v))


def _array(field, maximum=256):
    schema = {"type": "array", "items": field.schema}
    if maximum is not None:
        schema["maxItems"] = maximum
    return Field(schema, lambda v: type(v) is list and (maximum is None or len(v) <= maximum)
                 and all(field.accepts(x) for x in v))


def _object(properties, required=(), *, extra=True):
    schema = {"type": "object", "properties": {k: f.schema for k, f in properties.items()},
              "required": list(required), "additionalProperties": extra}
    return Field(schema, lambda v: type(v) is dict and set(required) <= set(v)
                 and (extra or set(v) <= set(properties))
                 and all(f.accepts(v[k]) for k, f in properties.items() if k in v))


def _mapping(field):
    return Field({"type": "object", "additionalProperties": field.schema},
                 lambda v: type(v) is dict and all(type(k) is str and field.accepts(x) for k, x in v.items()))


def _shape(properties):
    return _object(properties, tuple(properties), extra=False)


def _union(*fields):
    return Field({"anyOf": [f.schema for f in fields]}, lambda v: any(f.accepts(v) for f in fields))


def _integer(minimum=0, maximum=None):
    schema = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return Field(schema, lambda v: type(v) is int and v >= minimum and (maximum is None or v <= maximum))


_DEFINITIONS = {}


def _named(name, field):
    _DEFINITIONS[name] = field.schema
    return Field({"$ref": "#/$defs/" + name}, field.accepts)


_TEXT = _string()
_ID = _string(pattern=r"^[a-z0-9][a-z0-9_-]{0,95}$", maximum=96)
_TASK_ID = _string(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$", maximum=64)
_HASH = _string(pattern=r"^[0-9a-f]{64}$", maximum=64)
_INTEGER = _integer()
_NUMBER = Field({"type": "number", "minimum": 0},
                lambda v: (type(v) is int or type(v) is float and math.isfinite(v)) and v >= 0)
_BOOL = Field({"type": "boolean"}, lambda v: type(v) is bool)
_ANY = Field({}, lambda v: True)  # Provider usage is opaque additive JSON, not a billing attestation.
_DICT = Field({"type": "object"}, lambda v: type(v) is dict)
_TECHNIQUE_ID = _string(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", maximum=64)
_STORY_TAG = _string(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$", maximum=64)
_PACK_VERSION = _string(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$", maximum=32)
_WRITING_PHASE = _enum("concept", "draft", "plan-scene", "reader-review", "continuity-review", "revise")
_TECHNIQUE_SELECTION = _named("techniqueSelection", _shape({"pack_id": _TECHNIQUE_ID,
    "pack_version": _PACK_VERSION, "pack_sha256": _HASH, "technique_ids": _array(_TECHNIQUE_ID, 16)}))
_TECHNIQUE_FIELDS = {"technique_id": _TECHNIQUE_ID,
    "title": _string(maximum=120), "phases": _array(_WRITING_PHASE, 6),
    "applies_when": _string(maximum=2048), "guidance": _string(maximum=2048),
    "limitations": _array(_string(maximum=1024), 8), "review_criteria": _array(_string(maximum=1024), 8)}
_TECHNIQUE = _named("writingTechnique", _object({**_TECHNIQUE_FIELDS,
    "applicability": _shape({"tasks": _array(_TECHNIQUE_ID, 8), "story_tags": _array(_TECHNIQUE_ID, 16)})},
    tuple(_TECHNIQUE_FIELDS), extra=False))
_PACK_FIELDS = {"pack_id": _TECHNIQUE_ID, "pack_version": _PACK_VERSION,
    "title": _string(maximum=120), "summary": _string(maximum=1024)}
_PACK_METADATA = _named("techniquePackMetadata", _shape({**_PACK_FIELDS, "sha256": _HASH,
    "phases": _array(_WRITING_PHASE, 6), "technique_ids": _array(_TECHNIQUE_ID, 16)}))
_TECHNIQUE_PACK = _named("techniquePack", _shape({**_PACK_FIELDS,
    "schema_version": _enum("writing-assistant-technique-pack/1"), "sha256": _HASH,
    "guidance": _string(maximum=2048), "phase_guidance": _shape({name: _string(maximum=2048) for name in
        ("concept", "draft", "plan-scene", "reader-review", "continuity-review", "revise")}),
    "techniques": _array(_TECHNIQUE, 16)}))
_TECHNIQUE_SNAPSHOT = _named("techniqueSnapshot", _shape({
    "schema_version": _enum("writing-assistant-techniques/1"), "phase": _WRITING_PHASE,
    "packs": _array(_shape({"pack_id": _TECHNIQUE_ID, "pack_version": _PACK_VERSION, "pack_sha256": _HASH,
        "title": _string(maximum=120), "guidance": _string(maximum=2048),
        "phase_guidance": _string(maximum=2048), "techniques": _array(_TECHNIQUE, 16)}), 8)}))
_TECHNIQUE_CATALOG = _named("techniqueCatalog", _shape({"contract": _enum("writing-assistant-technique-catalog/1"),
    "packs": _array(_PACK_METADATA, 32), "model_calls": _enum(0)}))
_TECHNIQUE_VIEW = _named("techniqueView", _shape({"contract": _enum("writing-assistant-technique-view/1"),
    "pack": _TECHNIQUE_PACK, "model_calls": _enum(0)}))
_TECHNIQUE_SUGGESTIONS = _named("techniqueSuggestions", _shape({
    "contract": _enum("writing-assistant-technique-suggestions/1"), "phase": _WRITING_PHASE,
    "task": _TECHNIQUE_ID, "story_tags": _array(_STORY_TAG, 16), "limit": _integer(0, 3),
    "suggestions": _array(_shape({"pack_id": _TECHNIQUE_ID, "pack_version": _PACK_VERSION,
        "pack_sha256": _HASH, "technique_id": _TECHNIQUE_ID, "title": _string(maximum=120),
        "matched_tags": _array(_STORY_TAG, 16), "reasons": _array(_TEXT, 8)}), 3),
    "suggested_selection": _array(_TECHNIQUE_SELECTION, 3), "omitted_matches": _INTEGER,
    "selection_applied": _enum(False), "model_calls": _enum(0)}))


def _timestamp(value, maximum=64):
    if type(value) is not str or len(value) > maximum:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


_TIME = Field({"type": "string", "format": "date-time", "maxLength": 64}, _timestamp)
_REFERENCE = _named("recordReference", _object({"contract": _enum("creative-records/1"),
    "project_id": _ID, "record_id": _ID, "version_id": _ID, "sha256": _HASH},
    ("contract", "project_id", "record_id", "version_id", "sha256"), extra=False))
_RECORD_TIME = Field({"type": "string", "format": "date-time", "maxLength": 128},
                     lambda v: _timestamp(v, 128))
_RANGE = _named("halfOpenRange", Field({"type": "array", "prefixItems": [_INTEGER.schema, _INTEGER.schema],
    "items": False, "minItems": 2, "maxItems": 2}, lambda v: type(v) is list and len(v) == 2
    and all(_INTEGER.accepts(x) for x in v) and v[0] <= v[1]))
_SOURCE = _shape({"authorship": _enum("user", "agent", "mixed", "unknown"), "origin": _nullable(_TEXT)})
_EXTERNAL = _shape({"producer": _ID, "version": _string(maximum=128),
                    "path": _string(maximum=None), "sha256": _HASH})
_BODY = _shape({"storage": _enum("inline", "reference"), "sha256": _HASH,
               "size": _integer(maximum=16777216), "reference": _nullable(_EXTERNAL)})
_KIND = _enum("idea", "fragment", "draft", "setting", "decision", "feedback", "prose")
_DISPLAY_FIELDS = {"ref": _REFERENCE, "title": _TEXT, "kind": _KIND, "work_id": _nullable(_ID),
    "received_at": _RECORD_TIME, "source": _SOURCE, "parent": _nullable(_REFERENCE), "related": _array(_REFERENCE, 64)}
_DISPLAY = _named("recordListItem", _object({**_DISPLAY_FIELDS,
    "excerpt": _string(maximum=160), "excerpt_complete": _BOOL, "excerpt_range": _RANGE},
    tuple(_DISPLAY_FIELDS), extra=False))
_METADATA = _named("recordMetadata", _shape({"contract": _enum("creative-records/1"),
    "project_id": _ID, "record_id": _ID, "version_id": _ID, "operation_id": _ID,
    "title": _TEXT, "kind": _KIND, "work_id": _nullable(_ID), "source": _SOURCE,
    "audiences": _array(_ID, None), "original_created_at": _nullable(_RECORD_TIME), "received_at": _RECORD_TIME,
    "parent": _nullable(_REFERENCE), "related": _array(_REFERENCE, 64), "body": _BODY}))
_RECORD_WRITE = _named("recordWriteReceipt", _shape({"status": _enum("created", "retry"), "ref": _REFERENCE}))
_RECORD_READ = _named("recordReadReceipt", _shape({"status": _enum("saved-original"), "ref": _REFERENCE}))


def _base64_body(value):
    if type(value) is not str or len(value) > 22369624:
        return False
    try:
        return len(base64.b64decode(value, validate=True)) <= 16777216
    except ValueError:
        return False


_RECORD_SHOW = _named("recordShow", _shape({"ref": _REFERENCE, "metadata": _METADATA,
    "body_base64": Field({"type": "string", "contentEncoding": "base64", "maxLength": 22369624},
                         _base64_body)}))
_RECORD_PAGE = _named("recordPage", _shape({"items": _array(_DISPLAY, 200), "total": _INTEGER,
    "next_cursor": _nullable(_string(maximum=512)), "range": _RANGE, "originals_truncated": _enum(False)}))
_RECORD_LIST = _named("recordLegacyList", _shape({"versions": _array(_METADATA, None)}))
_RECORD_HISTORY_FIELDS = {"record_id": _ID, "versions": _array(_DISPLAY, None),
    "latest_stored": _REFERENCE, "continuation_selection": _enum(None), "adoption": _enum("not_determined_by_records")}
_SCAN_FIELDS = {"total": _enum(None), "next_cursor": _nullable(_string(maximum=512)), "range": _RANGE,
    "originals_truncated": _enum(False), "scan": _shape({"scanned": _INTEGER, "complete": _BOOL})}
_RECORD_LIST_RESULT = _named("recordList", _union(_RECORD_LIST,
    _shape({"versions": _array(_METADATA, 200), **_SCAN_FIELDS})))
_RECORD_SEARCH = _named("recordSearchPage", _union(_RECORD_PAGE,
    _shape({"items": _array(_DISPLAY, 200), **_SCAN_FIELDS})))
_RECORD_LEGACY_HISTORY = _named("recordLegacyHistory", _shape(_RECORD_HISTORY_FIELDS))
_RECORD_HISTORY = _named("recordHistory", _union(_RECORD_LEGACY_HISTORY,
    _shape({**_RECORD_HISTORY_FIELDS, "versions": _array(_DISPLAY, 200), "total": _INTEGER,
        "next_cursor": _nullable(_string(maximum=512)), "range": _RANGE, "originals_truncated": _enum(False)})))
_RECORD_INDEX = _named("recordIndexReceipt", _shape({"index_sha256": _HASH, "versions": _INTEGER}))
_RECORD_ROUTES = _named("recordRoutesReceipt", _shape({"versions": _INTEGER}))
_BOOKMARK_REFERENCE = _named("bookmarkReference", _shape({"contract": _enum("creative-continuation/1"),
    "project_id": _ID, "bookmark_id": _ID, "sha256": _HASH}))
_QUESTION = _shape({"text": _TEXT, "source": _nullable(_REFERENCE)})
_MATERIAL = _shape({"ref": _REFERENCE, "range": _nullable(_RANGE)})
_BOOKMARK_WRITE = _named("bookmarkWriteReceipt", _shape({"status": _enum("created", "retry"), "bookmark": _BOOKMARK_REFERENCE}))
_BOOKMARK = _named("bookmark", _shape({"contract": _enum("creative-continuation/1"), "project_id": _ID,
    "bookmark_id": _ID, "operation_id": _ID, "request_sha256": _HASH, "received_at": _RECORD_TIME,
    "audience": _ID, "selected": _REFERENCE, "stop": _nullable(_INTEGER), "decisions": _array(_REFERENCE, 128),
    "questions": _array(_QUESTION, 128), "materials": _array(_MATERIAL, 128), "baseline": _nullable(_string(maximum=256))}))
_BOOKMARK_ITEM = _shape({"bookmark": _BOOKMARK_REFERENCE, "selected": _REFERENCE, "received_at": _RECORD_TIME,
    "operation_id": _ID, "stop": _nullable(_INTEGER), "baseline": _nullable(_string(maximum=256))})
_BOOKMARK_PAGE = _named("bookmarkPage", _shape({"contract": _enum("creative-continuation/1"),
    "project_id": _ID, "audience": _ID, "items": _array(_BOOKMARK_ITEM, 200), "total": _INTEGER,
    "more_available": _BOOL, "model_calls": _enum(0)}))
_PURPOSE = _enum("selected_draft", "decision", "explicit_material", "question_source")
_USE = _object({"purpose": _PURPOSE, "question_index": _INTEGER}, ("purpose",), extra=False)
_PIECE = _shape({"ref": _REFERENCE, "range": _RANGE, "purpose": _PURPOSE, "uses": _array(_USE, 129),
                 "text": _string(maximum=16777216), "complete": _BOOL})
_CONTEXT = _named("continuationContext", _shape({"contract": _enum("creative-continuation/1"),
    "project_id": _ID, "audience": _ID, "bookmark": _BOOKMARK_REFERENCE, "selected": _REFERENCE,
    "stop": _nullable(_INTEGER), "offset_unit": _enum("unicode_code_points_utf8_including_bom"),
    "questions": _array(_QUESTION, 128), "baseline": _nullable(_string(maximum=256)), "pieces": _array(_PIECE, 129),
    "omissions": _array(_shape({"ref": _REFERENCE, "included_range": _RANGE}), 129),
    "adoption": _enum("not_determined_by_records"), "model_calls": _enum(0)}))

_DIAGNOSTIC_REFERENCE = _named("diagnosticReference", _shape({"contract": _enum("writing-diagnostics/1"),
    "project_id": _ID, "bucket": _HASH, "case_id": _ID, "revision": _integer(1, 256), "sha256": _HASH}))
_EVIDENCE = _named("diagnosticEvidence", _shape({"revision": _integer(1, 256), "sha256": _HASH,
    "original_sha256": _HASH, "bytes": _integer(1, 1048576), "original_bytes": _integer(1),
    "redacted": _BOOL, "truncated": _BOOL, "exact_original": _BOOL}))
_CONFIDENCE = _enum("unknown", "hypothesis", "confirmed")
_DIAGNOSTIC_SUMMARY_FIELDS = {"ref": _DIAGNOSTIC_REFERENCE, "component": _ID, "operation": _ID,
    "category": _ID, "signature": _HASH, "fingerprint": _HASH, "confidence": _CONFIDENCE,
    "disposition": _enum("advisory", "blocker"), "status": _enum("open", "resolved", "withdrawn"),
    "expires_at": _nullable(_TIME), "summary": _enum("Locally retained diagnostic case.")}
_DIAGNOSTIC_SUMMARY = _named("diagnosticSummary", _shape(_DIAGNOSTIC_SUMMARY_FIELDS))
_FACT_NAMES = ("environment", "code_state", "inputs", "configuration", "trigger")
_DIAGNOSTIC_BINDING = _named("diagnosticBinding", _shape({"project_id": _ID, "component": _ID,
    "operation": _ID, "category": _ID, "revision": _HASH, "branch": _nullable(_HASH), "worktree": _nullable(_HASH),
    **{name: _mapping(_HASH) for name in _FACT_NAMES},
    "missing": _array(_enum(*_FACT_NAMES, "revision", "branch", "worktree"), 8)}))
_DIAGNOSTIC_EVENT = _shape({"kind": _enum("diagnosis", "verification", "resolution", "observation"),
    "note": _TEXT, "result": _nullable(_enum("pass", "fail", "inconclusive")), "at": _TIME, "fingerprint": _HASH})
_DIAGNOSTIC_WRITE = _named("diagnosticWriteReceipt", _shape({"status": _enum("created", "existing", "revised"),
    "ref": _DIAGNOSTIC_REFERENCE, "evidence": _array(_EVIDENCE, 16)}))
_DIAGNOSTIC_SHOW_FIELDS = {"contract": _enum("writing-diagnostics/1"),
    "case": _DIAGNOSTIC_SUMMARY, "evidence": _array(_EVIDENCE, 16), "binding": _DIAGNOSTIC_BINDING,
    "parent": _nullable(_DIAGNOSTIC_REFERENCE)}
_DIAGNOSTIC_METADATA = _named("diagnosticMetadata", _shape({**_DIAGNOSTIC_SHOW_FIELDS, "event": _enum(None),
    "diagnosis": _shape({"confidence": _CONFIDENCE, "summary": _enum("Available by explicit evidence read.")})}))
_DIAGNOSTIC_EXPLICIT = _named("diagnosticExplicitEvidence", _shape({**_DIAGNOSTIC_SHOW_FIELDS,
    "event": _nullable(_DIAGNOSTIC_EVENT), "diagnosis": _shape({"confidence": _CONFIDENCE, "summary": _TEXT}),
    "summary": _TEXT, "resolution": _TEXT,
    "contents": _array(_shape({"revision": _integer(1, 256), "text": _string(maximum=1048576), "exact_original": _BOOL}), 16)}))
_DIAGNOSTIC_SHOW = _named("diagnosticShow", _union(_DIAGNOSTIC_METADATA, _DIAGNOSTIC_EXPLICIT))
_DIAGNOSTIC_MATCH = _object({**_DIAGNOSTIC_SUMMARY_FIELDS, "blocking": _BOOL, "reusable": _BOOL,
    "invalidation": _array(_TEXT, 32), "optional_verification_reusable": _BOOL},
    (*_DIAGNOSTIC_SUMMARY_FIELDS, "blocking", "reusable", "invalidation", "optional_verification_reusable"), extra=False)
_PREFLIGHT = _named("diagnosticPreflight", _shape({"contract": _enum("writing-diagnostics/1"),
    "blocking": _BOOL, "matches": _array(_DIAGNOSTIC_MATCH, 50), "next_cursor": _nullable(_ID),
    "coverage": _enum("complete", "degraded"), "warnings": _array(_TEXT, 64), "scanned": _INTEGER,
    "history": _enum("present", "absent", "unavailable"), "skipped_checks": _array(_TEXT, 64),
    "retry_authorized": _enum(False), "decision": _enum("blocked", "reduced_coverage", "advisory", "clear")}))
_DIAGNOSTIC_PAGE = _named("diagnosticPage", _shape({"contract": _enum("writing-diagnostics/1"),
    "items": _array(_DIAGNOSTIC_SUMMARY, 50), "next_cursor": _nullable(_ID)}))
_PENDING_ID = _string(pattern=r"^[pd]-[0-9a-f]{32}$", maximum=34)
_PENDING = _named("diagnosticPending", _shape({"contract": _enum("writing-diagnostics/1"),
    "items": _array(_shape({"pending_id": _PENDING_ID, "state": _enum("incomplete", "retention", "ready")}), 64)}))
_PRUNED = _shape({"status": _enum("pruned"), "case_id": _ID})
_DIAGNOSTIC_PRUNE = _named("diagnosticPruneReceipt", _PRUNED)
_RECOVER = _named("diagnosticRecoveryReceipt", _union(
    _shape({"status": _enum("discarded"), "pending_id": _PENDING_ID}),
    _shape({"status": _enum("recovered"), "ref": _DIAGNOSTIC_REFERENCE}), _PRUNED))
_METRICS = _named("observationSummary", _object({
    "elapsed": _object({"value": _nullable(_NUMBER), "unit": _enum("seconds"),
        "scope": _enum("local_codex_adapter_after_qualification")}, ("value", "unit", "scope"), extra=False),
    "usage_status": _enum("reported", "unavailable", "redacted"),
    "cost": _object({"status": _enum("unknown"), "amount": _enum(None), "currency": _enum(None)},
                    ("status", "amount", "currency"), extra=False)}, ("elapsed", "usage_status", "cost"), extra=False))
_MODEL_STATUS = _enum("not_dispatched", "unknown", "completed", "codex_missing", "capability_unsupported",
                     "codex_model_failure", "codex_timeout", "codex_cancelled", "codex_malformed", "codex_unknown")
_STATE = _enum("prepared", "uncertain", "model_recorded", "result_incomplete", "completed", "model_failed",
               "materialization_conflict", "blocked")
_LOCAL_STATUS = _enum("not_started", "pending", "completed", "not_applicable", "conflict")
_RECEIPT = _named("taskReceipt", _object({"plan_sha256": _HASH, "state": _STATE,
    "model_status": _MODEL_STATUS, "materialization_status": _LOCAL_STATUS, "status": _TEXT,
    "references": _mapping(_REFERENCE), "observation": _REFERENCE, "content": _REFERENCE,
    "provenance": _REFERENCE, "relation_record": _REFERENCE, "adopted": _enum(False),
    "usage": _ANY, "model_observed": _nullable(_TEXT), "model_requested": _nullable(_TEXT),
    "local_process_stopped": _BOOL, "backend_stop_confirmed": _BOOL,
    "observation_summary": _METRICS}, ("plan_sha256", "state", "model_status", "materialization_status", "status")))
_RUNTIME = _named("localRuntime", _object({
    "state": _enum("local_operation_active", "no_local_operation_observed", "unknown"),
    "task_lock": _enum("held", "available", "missing"), "observed_at": _TIME,
    "reservation_received_at": _TIME, "seconds_since_reservation": _nullable(_NUMBER),
    "backend_status": _enum("unknown")}, ("state", "task_lock", "observed_at", "reservation_received_at",
                                         "seconds_since_reservation", "backend_status"), extra=False))
_TIMING = _named("taskOperationTiming", _object({"status": _enum("recorded"), "sample": _enum("first_observed"),
    "operation": _enum("task execute", "task reconcile"), "elapsed_seconds": _NUMBER, "clock": _enum("monotonic"),
    "scope": _enum("local_task_operation_before_timing_persistence"),
    "outcome": _enum("prepared", "blocked", "completed", "model_failed", "materialization_conflict",
                     "model_recorded", "result_incomplete", "uncertain", "error"),
    "code": _string(pattern=r"^[a-z0-9_]{1,128}$", maximum=128), "record": _REFERENCE},
    ("status", "sample", "operation", "elapsed_seconds", "clock", "scope", "outcome", "record"), extra=False))
_TIMINGS = _named("taskOperationTimings", _object({key: _TIMING for key in ("preflight", "execute", "reconcile")}, extra=False))
_TIMING_UNAVAILABLE = _shape({"status": _enum("unavailable"), "code": _enum("timing_recording_failed")})
_TASK_FIELDS = {"contract": _enum("writing-assistant-task/1"), "task_id": _TASK_ID, "attempt_id": _ID,
    "plan_sha256": _HASH, "plan": _REFERENCE, "status": _STATE, "model_status": _MODEL_STATUS,
    "materialization_status": _LOCAL_STATUS, "evidence": _mapping(_REFERENCE), "result": _nullable(_RECEIPT),
    "adopted": _enum(False), "phase": _enum("concept", "draft", "plan-scene", "reader-review", "continuity-review", "revise"),
    "bindings": _array(_object({"uri": _string(maximum=2048), "ref": _REFERENCE}, ("uri", "ref"), extra=False), 32),
    "ranges": _array(_object({"uri": _string(maximum=2048), "start": _INTEGER, "end": _INTEGER},
                            ("uri", "start", "end"), extra=False), 32),
    "relations": _DICT, "diagnostics": _nullable(_DICT), "model_requested": _nullable(_TEXT),
    "reasoning_effort_requested": _nullable(_enum("low", "medium", "high", "xhigh", "max", "ultra")),
    "actions": _array(_enum("execute", "inspect", "reconcile"), 3), "model_calls": _enum(0, 1),
    "dispatch_attempts": _enum(0, 1), "local_runtime": _RUNTIME, "context": _DICT,
    "qualification": _DICT, "code": _string(maximum=128), "operation_timings": _TIMINGS,
    "timing_recording": _TIMING_UNAVAILABLE}
_CORE = ("contract", "task_id", "attempt_id", "plan_sha256", "plan", "status", "model_status",
         "materialization_status", "evidence", "adopted", "phase", "model_requested",
         "reasoning_effort_requested", "actions", "model_calls")
_FULL = _named("taskFullView", _object(_TASK_FIELDS, (*_CORE, "result", "bindings", "ranges", "relations", "diagnostics")))
_COMPACT = _named("taskCompactReceipt", _object({**_TASK_FIELDS, "view": _enum("compact"),
    "omitted_fields": _array(_string(maximum=64), 16),
    "diagnostics_summary": _DICT,
    "details": _object({"inspect_required_bytes": _INTEGER, "result": _REFERENCE, "receipt": _REFERENCE,
                        "diagnostics_operation": _enum("task diagnostics")},
                       ("inspect_required_bytes",), extra=False)}, (*_CORE, "view", "omitted_fields", "details")))
_TASK = _named("taskView", Field({"anyOf": [_FULL.schema, _COMPACT.schema]},
                                lambda v: _FULL.accepts(v) or _COMPACT.accepts(v)))
_TASK_DIAGNOSTICS = _named("taskDiagnostics", _object({"contract": _enum("writing-assistant-task-diagnostics/1"),
    "task_id": _TASK_ID, "plan_sha256": _HASH, "context": _DICT, "preflight": _nullable(_PREFLIGHT),
    "validation": _object({"plan_binding": _enum("verified"), "selected_record_metadata": _enum("verified"),
        "selected_content_bytes": _enum("not_read"), "external_originals": _enum("not_read"),
        "prompt_bytes": _enum("not_read"), "parent_cas": _enum("not_checked")},
        ("plan_binding", "selected_record_metadata", "selected_content_bytes", "external_originals", "prompt_bytes", "parent_cas")),
    "model_calls": _enum(0), "dispatch_attempts": _enum(0)},
    ("contract", "task_id", "plan_sha256", "context", "preflight", "validation", "model_calls", "dispatch_attempts")))

_PURPOSE = _shape({"aim": _string(maximum=16384), "open_choices": _array(_string(maximum=2048), 16)})
_REVIEW_POLICY = _shape({"material_action": _enum("advisory", "hold", "revise"), "max_revisions": _integer(0, 1)})
_WORKFLOW_OUTPUT_FIELDS = {"step": _integer(0, 100), "chapter": _integer(0, 20000),
    "phase": _WRITING_PHASE, "task_id": _TASK_ID, "task_plan": _REFERENCE, "receipt": _REFERENCE,
    "content": _REFERENCE, "relation_record": _REFERENCE}
_WORKFLOW_OUTPUT = _named("workflowOutput", _object({**_WORKFLOW_OUTPUT_FIELDS,
    "review_decision": _REFERENCE, "review_repair": _REFERENCE, "context": _REFERENCE, "purpose": _PURPOSE},
    tuple(_WORKFLOW_OUTPUT_FIELDS), extra=False))
_WORKFLOW_TASK_FIELDS = {"task_id": _TASK_ID, "plan_sha256": _HASH,
    "plan": _REFERENCE, "chapter": _integer(0, 20000), "phase": _WRITING_PHASE, "status": _STATE,
    "model_status": _MODEL_STATUS, "materialization_status": _LOCAL_STATUS,
    "actions": _array(_enum("execute", "inspect", "reconcile"), 3)}
_WORKFLOW_TASK = _named("workflowCurrentTask", _object({**_WORKFLOW_TASK_FIELDS,
    "context": _REFERENCE, "purpose": _PURPOSE}, tuple(_WORKFLOW_TASK_FIELDS), extra=False))
_WORKFLOW = _named("writingWorkflow", _object({"contract": _enum("writing-assistant-workflow/1"),
    "workflow_id": _TASK_ID, "project_id": _TASK_ID, "plan_sha256": _HASH, "plan": _REFERENCE,
    "checkpoint": _nullable(_REFERENCE), "checkpoint_sha256": _nullable(_HASH),
    "status": _enum("ready", "awaiting_task", "blocked", "completed"),
    "progress": _shape({"completed_steps": _integer(0, 101), "total_steps": _integer(1, 101),
        "completed_chapters": _integer(0, 20), "total_chapters": _integer(1, 20),
        "prepared_tasks": _integer(0, 101), "max_model_calls": _integer(1, 101)}),
    "current_task": _nullable(_WORKFLOW_TASK), "outputs": _array(_WORKFLOW_OUTPUT, 101),
    "actions": _array(_enum("next", "inspect", "task execute", "task inspect", "decide"), 2),
    "review_policy": _REVIEW_POLICY, "hold": _nullable(_shape({"chapter": _integer(1, 20000),
        "concerns": _array(_shape({"review_decision": _REFERENCE, "observation_id": _ID}), 64)})),
    "decisions": _array(_REFERENCE, 64), "updates": _array(_REFERENCE, 64), "review_repairs": _array(_REFERENCE, 64),
    "technique_suggestions": _nullable(_TECHNIQUE_SUGGESTIONS),
    "skipped_steps": _array(_integer(0, 100), 20),
    "adopted": _enum(False), "world_facts_written": _enum(False), "model_calls": _enum(0), "dispatch_attempts": _enum(0),
    "code": _enum("workflow_task_blocked", "workflow_review_hold", "authority_changed"), "view": _enum("compact"),
    "omitted_fields": _array(_enum("outputs"), 1),
    "details": _shape({"outputs_checkpoint": _nullable(_REFERENCE), "output_count": _integer(0, 101)})},
    ("contract", "workflow_id", "project_id", "plan_sha256", "plan", "checkpoint", "checkpoint_sha256", "status",
     "progress", "current_task", "outputs", "actions", "adopted", "world_facts_written", "model_calls", "dispatch_attempts"), extra=False))
_STORY_STATE = _named("storyState", _object({"contract": _enum("writing-assistant-story-state/1"),
    "state_id": _TASK_ID, "revision": _INTEGER, "reference": _REFERENCE, "snapshot": _DICT,
    "current": _BOOL, "model_calls": _enum(0), "world_facts_written": _enum(False)},
    ("contract", "state_id", "revision", "reference", "snapshot", "model_calls", "world_facts_written"), extra=False))

_CONFIGURATION = _named("projectConfiguration", _shape({"schema_version": _enum(1), "project_id": _TASK_ID,
    "data_dir": _string(maximum=16384), "writing_mode": _enum("lotus", "none"),
    "world_sandbox": _BOOL, "codex_adapter": _enum("codex-exec/1")}))
_CONFIG_FIELDS = {"effective": _CONFIGURATION, "source": _enum("project-config"), "sha256": _HASH}
_CONFIG_SNAPSHOT = _named("configurationSnapshot", _shape(_CONFIG_FIELDS))
_CONFIG_CHANGE = _named("configurationChange", _shape({**_CONFIG_FIELDS, "new_context_required": _BOOL,
    "message": _enum("Each generation uses a new context; changing configuration does not erase an existing chat.")}))
_CONFIG_RESULT = _named("configurationResult", _union(_CONFIG_SNAPSHOT, _CONFIG_CHANGE))
_CHECK_REQUEST = _named("requestCheck", _shape({"status": _enum("valid"), "executed": _enum(False)}))


def _valid_request(value):
    from .core.interface import validate_request
    try:
        validate_request(value)
        return True
    except (AssistantError, ValueError, TypeError, KeyError, RecursionError):
        return False


_URI_REFERENCE = _shape({"uri": _string(maximum=2048), "sha256": _HASH})
_PACKET_RELATIONS = _shape({"draft": _nullable(_URI_REFERENCE),
    "feedback": _array(_shape({"reference": _URI_REFERENCE, "target": _URI_REFERENCE}), 32)})
_MATERIAL_REFERENCE = _object({"uri": _string(maximum=2048), "sha256": _HASH,
    "purpose": _enum("current-writing", "world-projection", "actor-projection"),
    "role": _enum("request-material", "prior-prose", "current-draft", "feedback", "scene-projection"),
    "source_kind": _enum("user-supplied", "producer-output", "record-version", "sandbox-projection", "synthetic", "unknown"),
    "feedback_target": _URI_REFERENCE}, ("uri", "sha256", "purpose"), extra=False)
_REQUEST_SHAPE = _object({"schema_version": _enum("writing-assistant-request/1"), "request_id": _TASK_ID,
    "project_id": _TASK_ID, "kind": _enum("writing", "world-action"), "request": _string(maximum=1048576),
    "phase": _TASK_FIELDS["phase"], "materials": _array(_MATERIAL_REFERENCE, 32),
    "techniques": _array(_TECHNIQUE_SELECTION, 8)},
    ("schema_version", "request_id", "project_id", "kind", "request", "materials"), extra=False)
_REQUEST = _named("transportRequest", Field(_REQUEST_SHAPE.schema,
    lambda v: _REQUEST_SHAPE.accepts(v) and _valid_request(v)))
_PRODUCER_PACKET = _shape({"schema_version": _enum(1), "component_version": _enum("0.1.0"), "status": _enum("ready"),
    "request_id": _string(maximum=256), "selection": _shape({"version": _enum(1), "mode": _enum("lotus", "none")}),
    "phase": _TASK_FIELDS["phase"], "method_version": _enum(1, None),
    "context": _shape({"id": _string(maximum=256), "fresh": _BOOL, "frameworks_seen": _array(_string(maximum=128), 32)}),
    "context_assurance": _enum("caller-declared-not-host-authenticated"), "request": _string(maximum=1048576),
    "materials": _array(_shape({"reference": _URI_REFERENCE, "text": _string(maximum=1048576)}), 32),
    "instructions": _array(_string(maximum=None), 1), "packet_sha256": _HASH})
_PRODUCER_SHAPE = _shape({"contract": _shape({"id": _enum("writing-producer-request"), "version": _enum(1)}),
    "packet": _PRODUCER_PACKET,
    "sources": _array(_shape({"role": _TEXT, "kind": _TEXT, "reference": _URI_REFERENCE}), 32), "request_sha256": _HASH})


def _valid_producer(value):
    from writing_frameworks.provenance import validate_prepared
    try:
        validate_prepared(value)
        return True
    except (ValueError, TypeError, KeyError, RecursionError):
        return False


_PRODUCER = Field(_PRODUCER_SHAPE.schema, lambda v: _PRODUCER_SHAPE.accepts(v) and _valid_producer(v))
_PREPARED = _named("preparedPacket", _object({"schema_version": _enum("writing-assistant-packet/1"),
    "request": _REQUEST, "configuration": _CONFIG_SNAPSHOT, "context": _enum("new-per-request"),
    "status": _enum("prepared-unexecuted"), "sha256": _HASH,
    "materials": _array(_shape({"reference": _MATERIAL_REFERENCE, "text": _string(maximum=4194304)}), 32),
    "instructions": _array(_string(maximum=None), 9), "relations": _PACKET_RELATIONS, "producer_request": _PRODUCER,
    "techniques": _TECHNIQUE_SNAPSHOT},
    ("schema_version", "request", "configuration", "context", "status", "sha256", "materials", "instructions"), extra=False))
_DOCTOR_SCOPE = {"probe_scope": _enum("local-version-help-and-feature-flags"), "runtime_readiness": _enum("not_checked")}
_DOCTOR_FIELDS = {**_DOCTOR_SCOPE, "version": _nullable(_string(maximum=131072)), "surface": _enum("codex-exec"),
    "missing_flags": _array(_string(maximum=128), 32), "model_observed": _enum(None)}
_DOCTOR_EARLY = _shape({**_DOCTOR_SCOPE, "status": _enum("missing", "unknown", "unsupported"),
    "code": _enum("codex_missing", "capability_unsupported"), "live_supported": _enum(False)})
_DOCTOR_OBSERVED = _object({**_DOCTOR_FIELDS, "status": _enum("supported", "unknown", "unsupported"),
    "code": _nullable(_enum("capability_unsupported")), "live_supported": _BOOL,
    "launch_configuration": _enum("not_checked", "feature_flags_verified", "unsupported", "unknown"),
    "version_redacted": _enum(True)}, (*_DOCTOR_FIELDS, "status", "code", "live_supported", "launch_configuration"), extra=False)
_DOCTOR = _named("codexDoctor", _union(_DOCTOR_EARLY, _DOCTOR_OBSERVED))
_DIAGNOSTIC_FAILURE = _object({"primary_code": _string(maximum=128), "capture": _nullable(_DIAGNOSTIC_WRITE),
    "warnings": _array(_TEXT, 64), "skipped_checks": _array(_TEXT, 64), "next_action": _TEXT},
    ("primary_code", "warnings"), extra=False)
_EXECUTION_FIELDS = {"status": _enum("error", "not_dispatched", "unknown", "completed", "codex_missing", "capability_unsupported",
    "codex_model_failure", "codex_timeout", "codex_cancelled", "codex_malformed", "codex_unknown"),
    "references": _mapping(_REFERENCE), "observation": _REFERENCE, "adopted": _enum(False), "usage": _ANY,
    "model_observed": _nullable(_TEXT), "model_requested": _nullable(_TEXT),
    "model_selection_source": _nullable(_enum("explicit-command", "codex-cli-default-user-config-ignored")),
    "reasoning_effort_requested": _nullable(_enum("low", "medium", "high", "xhigh", "max", "ultra")),
    "reasoning_effort_observed": _nullable(_TEXT),
    "reasoning_effort_selection_source": _nullable(_enum("explicit-command", "codex-cli-default-user-config-ignored")),
    "local_process_stopped": _BOOL, "backend_stop_confirmed": _BOOL, "observation_summary": _METRICS,
    "content": _REFERENCE, "provenance": _REFERENCE, "relation_record": _REFERENCE,
    "relations": _object({"contract": _enum("writing-relations/1"), "output": _REFERENCE, "draft": _nullable(_REFERENCE),
        "draft_range": _nullable(_shape({"start": _INTEGER, "end": _INTEGER})),
        "feedback": _array(_shape({"reference": _REFERENCE, "target": _REFERENCE}), 32)},
        ("contract", "output", "draft", "feedback"), extra=False),
    "code": _string(maximum=128), "diagnostics": _DIAGNOSTIC_FAILURE,
    "phase": _enum("qualification"), "launched": _enum(False), "model_calls": _enum(0)}
_EXECUTION_RECEIPT = _named("executionReceipt", _object(_EXECUTION_FIELDS,
    ("status", "references", "observation", "adopted", "usage", "model_observed", "local_process_stopped", "backend_stop_confirmed"), extra=False))
_LEGACY_EXECUTE = _named("legacyExecution", _union(_EXECUTION_RECEIPT, _shape({"status": _enum("error"),
    "code": _enum("diagnostic_blocker"), "diagnostics": _PREFLIGHT, "model_calls": _enum(0), "adopted": _enum(False)})))
_SIGNED_NUMBER = Field({"type": "number"}, lambda v: type(v) is int or type(v) is float and math.isfinite(v))
_WORLD_STATUS = _named("worldStatus", _shape({"scope": _enum("owner-progress"), "model_calls": _enum(0),
    "replay_verified": _BOOL, "run_id": _TASK_ID, "issued": _INTEGER, "remaining": _INTEGER,
    "branches": _mapping(_shape({"version": _INTEGER, "cursor": _INTEGER,
        "actors": _mapping(_shape({"location": _TASK_ID, "coins": _SIGNED_NUMBER}))}))}))
_WORLD_SETTLE = _named("worldSettlement", _shape({"run_id": _TASK_ID, "world_id": _TASK_ID,
    "branch_id": _TASK_ID, "actor_id": _TASK_ID, "request_id": _TASK_ID, "base_version": _INTEGER,
    "status": _enum("accepted", "rejected"), "code": _nullable(_TEXT), "version": _INTEGER,
    "event_id": _nullable(_TASK_ID)}))
_WORLD_TIME = _named("worldTimeAdvance", _union(_shape({"scope": _enum("owner-progress"),
    "status": _enum("paused"), "code": _enum("stop_requested")}), _shape({"scope": _enum("owner-progress"),
    "status": _enum("completed", "paused"), "code": _nullable(_TEXT), "time": _INTEGER, "target": _INTEGER,
    "processed": _array(_TASK_ID, 128), "remaining_due": _INTEGER})))
_WORLD_ADVANCE = _named("worldAdvance", _union(_shape({"scope": _enum("owner-progress"),
    "run_id": _TASK_ID, "branch_id": _enum("main"), "status": _enum("completed", "paused"),
    "stop_requested": _BOOL, "completed_steps": _INTEGER, "planned_steps": _INTEGER, "advanced_steps": _integer(0, 16),
    "receipts": _array(_WORLD_SETTLE, 16), "execution_evidence": _array(_EXECUTION_RECEIPT, 16)}),
    _shape({"status": _enum("error"), "code": _string(maximum=128), "execution_evidence": _array(_EXECUTION_RECEIPT, 16), "run_id": _TASK_ID})))
_WORLD_REFERENCE = _named("worldProjectionReference", _shape({"uri": _string(pattern=r"^lotus-sandbox-projection:1:[0-9a-f]{64}$", maximum=91),
    "sha256": _HASH, "purpose": _enum("actor-projection", "world-projection")}))
_WORLD_SELECTION = _array(_array(_union(_string(maximum=None), _INTEGER), None), None)
_WORLD_BODY_FIELDS = {"schema_version": _enum("lotus-sandbox-projection/1"), "run_id": _TASK_ID,
    "world_id": _TASK_ID, "branch_id": _TASK_ID, "world_version": _INTEGER, "actor_id": _TASK_ID}
_WORLD_ACTOR_BODY = _shape({**_WORLD_BODY_FIELDS, "purpose": _enum("actor-projection"), "selection": _enum(None),
    "view": _shape({"actor_id": _TASK_ID, "profile": _nullable(_DICT), "trajectory": _array(_DICT, None), "observation": _DICT})})
_WORLD_SELECTED_BODY = _shape({**_WORLD_BODY_FIELDS, "purpose": _enum("world-projection"), "selection": _WORLD_SELECTION,
    "view": _array(_shape({"path": _array(_union(_string(maximum=None), _INTEGER), None),
        "value": _union(_enum(None), _BOOL, _SIGNED_NUMBER, _string(maximum=None))}), None)})
_WORLD_PROJECTION = _named("worldProjection", _shape({"reference": _WORLD_REFERENCE,
    "body": _union(_WORLD_ACTOR_BODY, _WORLD_SELECTED_BODY)}))
_WORLD_CAPTURE = _named("worldCaptureReceipt", _shape({"status": _enum("created", "retry"), "ref": _REFERENCE,
    "projection_reference": _WORLD_REFERENCE, "adopted": _enum(False), "model_calls": _enum(0)}))
_CAPABILITIES = _named("capabilities", _object({"schema_version": _enum("writing-assistant-capabilities/1"),
    "application_version": _string(maximum=128), "view": _enum("overview", "operation", "detail", "schema"),
    "schemas": _mapping(_object({"path": _TEXT, "schema": _DICT}, ("path",))),
    "operations": _array(_object({"operation": _TEXT, "output_schema": _nullable(_TEXT),
        "output_validation": _enum("core-fields", "json-fields-or-original-bytes", "original-bytes", "not-covered"),
        "output_variants": _array(_shape({"when": _TEXT, "transport": _enum("json", "bytes"),
            "schema": _nullable(_TEXT), "validation": _enum("core-fields", "bounded-original-bytes")}), 2)}, ("operation",)), 128)},
    ("schema_version", "application_version", "view", "schemas")))
_ERROR = _named("cliError", _object({"status": _enum("error"), "code": _string(maximum=128),
    "required_bytes": _INTEGER, "allowed_bytes": _INTEGER, "operation": _string(maximum=128),
    "effect_status": _enum("none", "unknown"), "task_id": _TASK_ID, "attempt_id": _ID, "workflow_id": _TASK_ID,
    "plan_sha256": _HASH, "checkpoint_sha256": _HASH, "case_id": _ID, "pending_id": _PENDING_ID, "project_id": _TASK_ID,
    "request_id": _TASK_ID, "run_id": _TASK_ID, "configuration_sha256": _HASH,
    "references": _mapping(_union(_REFERENCE, _BOOKMARK_REFERENCE, _DIAGNOSTIC_REFERENCE, _WORLD_REFERENCE))}, ("status", "code"), extra=False))

_OPERATIONS = {
    "init": ("configurationSnapshot", _CONFIG_SNAPSHOT), "config": ("configurationResult", _CONFIG_RESULT),
    "doctor": ("codexDoctor", _DOCTOR), "check-request": ("requestCheck", _CHECK_REQUEST),
    "prepare": ("preparedPacket", _PREPARED), "execute": ("legacyExecution", _LEGACY_EXECUTE),
    "world create": ("worldStatus", _WORLD_STATUS), "world status": ("worldStatus", _WORLD_STATUS),
    "world advance": ("worldAdvance", _WORLD_ADVANCE), "world advance-time": ("worldTimeAdvance", _WORLD_TIME),
    "world settle": ("worldSettlement", _WORLD_SETTLE), "world projection": ("worldProjection", _WORLD_PROJECTION),
    "world capture": ("worldCaptureReceipt", _WORLD_CAPTURE),
    **{name: ("taskView", _TASK) for name in ("task prepare", "task inspect", "task execute", "task reconcile")},
    "task diagnostics": ("taskDiagnostics", _TASK_DIAGNOSTICS), "capabilities": ("capabilities", _CAPABILITIES),
    "technique list": ("techniqueCatalog", _TECHNIQUE_CATALOG), "technique show": ("techniqueView", _TECHNIQUE_VIEW),
    "technique suggest": ("techniqueSuggestions", _TECHNIQUE_SUGGESTIONS),
    **{name: ("storyState", _STORY_STATE) for name in ("story-state create", "story-state revise", "story-state inspect")},
    **{name: ("writingWorkflow", _WORKFLOW) for name in ("workflow create", "workflow inspect", "workflow next", "workflow update", "workflow decide", "workflow repair-review")},
    **{name: ("recordWriteReceipt", _RECORD_WRITE) for name in ("records save", "records import-writer", "records import-actor")},
    "records read": ("recordReadReceipt", _RECORD_READ), "records show": ("recordShow", _RECORD_SHOW),
    "records recent": ("recordPage", _RECORD_PAGE), "records search": ("recordSearchPage", _RECORD_SEARCH),
    "records list": ("recordList", _RECORD_LIST_RESULT), "records history": ("recordHistory", _RECORD_HISTORY),
    "records rebuild-index": ("recordIndexReceipt", _RECORD_INDEX), "records bind-record-routes": ("recordRoutesReceipt", _RECORD_ROUTES),
    "records bookmark": ("bookmarkWriteReceipt", _BOOKMARK_WRITE), "records read-bookmark": ("bookmark", _BOOKMARK),
    "records bookmarks": ("bookmarkPage", _BOOKMARK_PAGE), "records context": ("continuationContext", _CONTEXT),
    **{name: ("diagnosticWriteReceipt", _DIAGNOSTIC_WRITE) for name in ("diagnostics capture", "diagnostics revise")},
    "diagnostics show": ("diagnosticShow", _DIAGNOSTIC_SHOW), "diagnostics preflight": ("diagnosticPreflight", _PREFLIGHT),
    "diagnostics query": ("diagnosticPage", _DIAGNOSTIC_PAGE), "diagnostics pending": ("diagnosticPending", _PENDING),
    "diagnostics recover": ("diagnosticRecoveryReceipt", _RECOVER), "diagnostics prune": ("diagnosticPruneReceipt", _DIAGNOSTIC_PRUNE),
}
_MUTATIONS = {"task prepare", "task execute", "task reconcile", "records save", "records read",
    "workflow create", "workflow next", "workflow update", "workflow decide", "workflow repair-review", "story-state create", "story-state revise",
    "records import-writer", "records import-actor", "records rebuild-index", "records bind-record-routes",
    "records bookmark", "diagnostics capture", "diagnostics revise", "diagnostics recover", "diagnostics prune",
    "init", "config", "execute", "world create", "world advance", "world advance-time", "world settle", "world capture"}


def schema_document():
    roots = {name: field.schema for name, field in _OPERATIONS.values()}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "writing-assistant-core-results/1", "title": "Core Agent workflow CLI results v1",
            "$defs": deepcopy(_DEFINITIONS), "anyOf": list(roots.values()) + [_ERROR.schema]}


def output_schema(operation):
    selected = _OPERATIONS.get(operation)
    return None if selected is None else "core-results#/$defs/" + selected[0]


class OutputContractError(AssistantError):
    def __init__(self, operation, value, *, mutation=None):
        super().__init__("output_contract_violation")
        changed = operation in _MUTATIONS if mutation is None else mutation is True
        self.safe_context = {"operation": operation, "effect_status": "unknown" if changed else "none"}
        if type(value) is dict:
            for key, field in (("task_id", _TASK_ID), ("attempt_id", _ID), ("plan_sha256", _HASH),
                               ("workflow_id", _TASK_ID), ("checkpoint_sha256", _HASH),
                               ("case_id", _ID), ("pending_id", _PENDING_ID), ("project_id", _TASK_ID),
                               ("request_id", _TASK_ID), ("run_id", _TASK_ID)):
                if key in value and field.accepts(value[key]):
                    self.safe_context[key] = value[key]
            refs = {}
            if _REFERENCE.accepts(value.get("plan")):
                refs["plan"] = value["plan"]
            if _REFERENCE.accepts(value.get("checkpoint")):
                refs["checkpoint"] = value["checkpoint"]
            for key in ("observation", "content", "provenance", "relation_record"):
                if _REFERENCE.accepts(value.get(key)):
                    refs[key] = value[key]
            for key in ("reference", "projection_reference"):
                if _WORLD_REFERENCE.accepts(value.get(key)):
                    refs[key] = value[key]
            for container in (value.get("effective"), value.get("request")):
                if type(container) is dict:
                    for key in ("project_id", "request_id"):
                        if _TASK_ID.accepts(container.get(key)):
                            self.safe_context[key] = container[key]
            if _HASH.accepts(value.get("sha256")) and operation in {"init", "config"}:
                self.safe_context["configuration_sha256"] = value["sha256"]
            for key, field in (("ref", _union(_REFERENCE, _DIAGNOSTIC_REFERENCE)), ("bookmark", _BOOKMARK_REFERENCE)):
                if field.accepts(value.get(key)):
                    refs[key] = value[key]
            for evidence in (value.get("evidence"), value.get("references")):
                if type(evidence) is dict:
                    for key in ("input", "stdout", "stderr", "output", "observation"):
                        if _REFERENCE.accepts(evidence.get(key)):
                            refs[key] = evidence[key]
            if refs:
                self.safe_context["references"] = refs


def validate_output(operation, value, *, include_evidence=None, requested_raw=False, mutation=None):
    """Check the declared JSON branch; uncovered operations are unchanged."""
    selected = _OPERATIONS.get(operation)
    if operation == "world resolve" or requested_raw is True and operation in {"records show", "world projection"}:
        raise OutputContractError(operation, value, mutation=mutation)
    field = None if selected is None else selected[1]
    if operation == "diagnostics show" and include_evidence is not None:
        field = _DIAGNOSTIC_EXPLICIT if include_evidence is True else _DIAGNOSTIC_METADATA
    if field is not None and not field.accepts(value):
        raise OutputContractError(operation, value, mutation=mutation)
    return value


def validate_raw_output(operation, body, *, requested=False):
    """Retain exact original bytes; RecordStore already checks reference integrity."""
    if (operation not in {"records show", "world projection", "world resolve"}
            or requested is not True or type(body) is not bytes or len(body) > 16777216):
        raise OutputContractError(operation, None)
    return body


def valid_operation_timings(value):
    """Share the fixed task timing shape with persisted-evidence validation."""
    return _TIMINGS.accepts(value)


def validate_error(value):
    return _ERROR.accepts(value)
