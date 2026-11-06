"""Local, bounded diagnostic cases; evidence is never an execution permit.

Callers supply selected observations and live authority. No Git, environment,
filesystem discovery, provider call or telemetry is performed. Cooperative POSIX
locks and SafeSession require the same stable namespace as Creative Records.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .core.errors import AssistantError
from .records.core import Scope, RecordsError
from .records.safeio import Budget, SafeSession, logical_root

CONTRACT = "writing-diagnostics/1"
UNSET = object()
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REV = re.compile(r"r([0-9]{8})\Z")
_CONTEXT = {"project_id", "component", "operation", "category", "revision",
            "environment", "code_state", "inputs", "configuration", "trigger", "branch", "worktree"}
_FACTS = ("environment", "code_state", "inputs", "configuration", "trigger")
_ROW = {"contract", "project_id", "bucket", "case_id", "revision", "parent", "created_at",
        "updated_at", "binding", "signature", "fingerprint", "summary", "confidence",
        "disposition", "status", "diagnosis", "resolution", "event", "verification",
        "expires_at", "evidence", "capture_sha256", "origin_sha256"}
_AUTHORITY = {"authority_failed", "authority_required", "not_available", "invalid_scope"}


class DiagnosticsError(AssistantError):
    """Stable error codes contain no original evidence or private paths."""

    def __init__(self, code):
        self.next_action = {
            "diagnostics_capacity": "review_withdrawn_case_retention_or_explicit_limits",
            "diagnostics_recovery_required": "inspect_pending_and_recover_or_discard",
            "diagnostics_conflict": "read_latest_reference_before_revising",
            "diagnostics_output_limit": "select_a_smaller_page_or_explicit_evidence_range",
            "diagnostics_busy": "retry_local_store_access_after_the_active_writer",
        }.get(code, "inspect_diagnostic_coverage_and_selected_inputs")
        super().__init__(code)


def _require(value, code="diagnostics_invalid_request"):
    if not value:
        raise DiagnosticsError(code)


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise DiagnosticsError("diagnostics_invalid_request") from None


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "diagnostics_corrupt")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: _require(False, "diagnostics_corrupt"))
    except (ValueError, UnicodeError, RecursionError):
        raise DiagnosticsError("diagnostics_corrupt") from None


def _identifier(value):
    _require(type(value) is str and _ID.fullmatch(value))
    return value


def _sha(value):
    _require(type(value) is str and _SHA.fullmatch(value), "diagnostics_corrupt")
    return value


def _time(value):
    _require(type(value) is str and len(value) <= 64)
    try:
        stamp = datetime.fromisoformat(value)
        _require(stamp.tzinfo is not None)
        return stamp
    except ValueError:
        raise DiagnosticsError("diagnostics_invalid_request") from None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, limit=4096):
    _require(type(value) is str)
    try:
        _require(len(value.encode("utf-8")) <= limit)
    except UnicodeError:
        raise DiagnosticsError("diagnostics_invalid_request") from None
    return value


def _redact(text, secrets=()):
    # Collection is explicit and minimal. These patterns are defense in depth,
    # not a general detector of private meaning in arbitrary prose.
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
                  "[REDACTED PRIVATE KEY]", text, flags=re.S)
    text = re.sub(r"(?i)\b(?:bearer\s+|sk-(?:proj-)?)[A-Za-z0-9_.~+/=-]{6,}", "[REDACTED]", text)
    text = re.sub(r'''(?i)(["']?\b(?:[a-z0-9_]*(?:password|passwd|secret|token|api_key|credential)[a-z0-9_]*)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)''',
                  r"\1[REDACTED]", text)
    text = re.sub(r"https?://[^\s<>\"']+", "[REDACTED URL]", text)
    text = re.sub(r"(?<!\w)[^\s/@]+@[^\s/@]+\.[^\s/@]+", "[REDACTED EMAIL]", text)
    text = re.sub(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^\s\"']+", "[REDACTED PATH]", text)
    return text


def _secrets(values):
    _require(isinstance(values, (tuple, list)) and len(values) <= 64)
    return tuple(_text(v, 4096) for v in values if v != "")


@dataclass(frozen=True)
class DiagnosticLimits:
    """Per-call and persistent bounds; raising these requires an explicit caller."""
    max_cases: int = 1024
    max_revisions: int = 64
    max_evidence_bytes: int = 65536
    max_total_bytes: int = 64 * 1024 * 1024
    max_pending: int = 16
    max_scan: int = 256
    read_bytes: int = 16 * 1024 * 1024
    seconds: int = 15

    def __post_init__(self):
        ceilings = {"max_cases": 4096, "max_revisions": 256, "max_evidence_bytes": 1024 * 1024,
                    "max_total_bytes": 512 * 1024 * 1024, "max_pending": 64,
                    "max_scan": 4096, "read_bytes": 128 * 1024 * 1024, "seconds": 60}
        for name, ceiling in ceilings.items():
            _require(type(getattr(self, name)) is int and 0 < getattr(self, name) <= ceiling)


def _binding(context, *, capture, secrets=()):
    _require(type(context) is dict and set(context) == _CONTEXT)
    result = {key: _identifier(context[key]) for key in ("project_id", "component", "operation")}
    category = context["category"]
    _require(category is not None or not capture)
    result["category"] = _identifier(category) if category is not None else None
    missing = []
    for name in ("revision", "branch", "worktree"):
        value = context[name]
        _require(value is None and name != "revision" or type(value) is str)
        if value is not None:
            _text(value, 1024)
            _require(_redact(value, secrets) == value, "diagnostics_sensitive_context")
            if not value.strip() or value.casefold() in {"unknown", "unverified"}:
                missing.append(name)
        result[name] = _hash(_json(value)) if value is not None else None
    for name in _FACTS:
        facts = context[name]
        _require(type(facts) is dict and len(facts) <= 32)
        result[name] = {}
        if not facts and name in {"environment", "code_state", "trigger"}:
            missing.append(name)
        for key, value in facts.items():
            _identifier(key)
            _require(not re.search(r"(?i)password|passwd|secret|token|api_key|credential", key),
                     "diagnostics_sensitive_context")
            _require(type(value) in (str, int, bool))
            if type(value) is str:
                _text(value, 1024)
                _require(_redact(value, secrets) == value, "diagnostics_sensitive_context")
                if not value.strip() or value.casefold() in {"unknown", "unverified"}:
                    missing.append(name)
            elif type(value) is int:
                _require(abs(value) < 2 ** 63)
            result[name][key] = _hash(_json(value))
    result["missing"] = sorted(set(missing))
    return result


def _bucket(binding):
    return _hash(_json([binding["component"], binding["operation"]]))


def _signature(binding):
    return _hash(_json([binding[key] for key in ("component", "operation", "category", "trigger")]))


class DiagnosticStore:
    """An explicitly linked user-owned store, independent of checkout/chat state."""

    def __init__(self, root, *, limits=None, clock=None, fault=None):
        _require(Path(root).is_absolute(), "diagnostics_explicit_root_required")
        self.root = logical_root(root)
        self.limits = limits or DiagnosticLimits()
        self.clock = clock or _now
        self.fault = fault or (lambda stage: None)

    def _project(self, scope):
        return "diagnostics/v1/" + _identifier(scope.project_id)

    def _verify(self, scope, *, write=False):
        _require(isinstance(scope, Scope), "authority_required")
        _require(scope.audience == "owner" and scope.record_ids is None, "invalid_scope")
        try:
            scope.verify(write=write)
        except RecordsError as exc:
            raise DiagnosticsError(exc.code) from None

    @contextmanager
    def _session(self, scope, *, write=False, allow_absent=False):
        self._verify(scope, write=write)
        _require(os.name == "posix", "diagnostics_unsupported_platform")
        io = None
        try:
            with SafeSession(self.root, Budget(file_bytes=max(self.limits.max_evidence_bytes, 65536),
                             input_bytes=self.limits.read_bytes, read_bytes=self.limits.read_bytes,
                             seconds=self.limits.seconds)) as io:
                io.diagnostics_published = False
                root_info = os.fstat(io.directory(()))
                _require(root_info.st_uid == os.getuid(), "authority_failed")
                project = self._project(scope)
                if write:
                    io.mkdir(project)
                parts = tuple(project.split("/"))
                for end in range(1, len(parts) + 1):
                    try:
                        info = os.fstat(io.directory(parts[:end]))
                    except FileNotFoundError:
                        if not allow_absent or write:
                            raise
                        # Only a missing optional namespace is empty history.
                        # Existing ancestors, root identity and live authority
                        # still pass the same checks; no directory is created.
                        self._verify(scope)
                        io._verify_dirs(parts[:end - 1])
                        yield io, None
                        self._verify(scope)
                        io._verify_dirs(parts[:end - 1])
                        return
                    _require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
                             "diagnostics_permissions")
                with self._lock(io, project):
                    self._verify(scope, write=write)
                    yield io, project
                    self._verify(scope, write=write)
                    io._verify_dirs(parts)
        except DiagnosticsError:
            if io is not None and io.diagnostics_published:
                raise DiagnosticsError("diagnostics_outcome_unknown") from None
            raise
        except (OSError, ValueError, RuntimeError):
            if io is not None and io.diagnostics_published:
                raise DiagnosticsError("diagnostics_outcome_unknown") from None
            raise DiagnosticsError("diagnostics_unavailable") from None

    @contextmanager
    def _lock(self, io, project):
        parts = tuple(project.split("/"))
        parent = io.directory(parts)
        handle = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=parent)
        try:
            row = os.fstat(handle)
            _require(stat.S_ISREG(row.st_mode) and row.st_nlink == 1 and row.st_mode & 0o077 == 0,
                     "diagnostics_permissions")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DiagnosticsError("diagnostics_busy") from None
            io._verify_dirs(parts)
            current = os.stat(".lock", dir_fd=parent, follow_symlinks=False)
            _require((row.st_dev, row.st_ino) == (current.st_dev, current.st_ino), "diagnostics_corrupt")
            yield
        finally:
            os.close(handle)

    def _names(self, io, path, limit):
        try:
            fd = io.directory(tuple(path.split("/")))
        except FileNotFoundError:
            return []
        names = []
        with os.scandir(fd) as rows:
            for row in rows:
                io.budget.tick()
                _require(len(names) < limit, "diagnostics_capacity")
                _require(row.is_dir(follow_symlinks=False), "diagnostics_corrupt")
                names.append(row.name)
        return sorted(names)

    def _inventory(self, io, project):
        """Stat bounded private entries without reading any evidence bodies."""
        total, entries, cases = 0, 0, 0
        def walk(path, depth):
            nonlocal total, entries, cases
            _require(depth <= 7, "diagnostics_corrupt")
            fd = io.directory(tuple(path.split("/")))
            with os.scandir(fd) as rows:
                for row in rows:
                    io.budget.tick()
                    entries += 1
                    _require(entries <= 32768, "diagnostics_capacity")
                    info = row.stat(follow_symlinks=False)
                    _require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
                             "diagnostics_permissions")
                    if stat.S_ISDIR(info.st_mode):
                        if path.startswith(project + "/buckets/") and depth == 2:
                            cases += 1
                        walk(path + "/" + row.name, depth + 1)
                    else:
                        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "diagnostics_corrupt")
                        total += info.st_size
        walk(project, 0)
        return total, cases

    def _ref(self, row):
        return {key: row[key] for key in ("contract", "project_id", "bucket", "case_id", "revision")} | {
            "sha256": _hash(_json(row))}

    def _reference(self, scope, ref):
        _require(type(ref) is dict and set(ref) == {"contract", "project_id", "bucket", "case_id", "revision", "sha256"})
        _require(ref["contract"] == CONTRACT, "diagnostics_unsupported_contract")
        _require(ref["project_id"] == scope.project_id, "not_available")
        _identifier(ref["case_id"])
        _sha(ref["bucket"])
        _sha(ref["sha256"])
        _require(type(ref["revision"]) is int and 1 <= ref["revision"] <= 256)
        return f'{self._project(scope)}/buckets/{ref["bucket"]}/{ref["case_id"]}'

    def _validate(self, row, scope):
        _require(type(row) is dict and set(row) == _ROW, "diagnostics_corrupt")
        _require(row["contract"] == CONTRACT and row["project_id"] == scope.project_id,
                 "diagnostics_corrupt")
        _identifier(row["case_id"])
        _require(type(row["revision"]) is int and 1 <= row["revision"] <= 256, "diagnostics_corrupt")
        binding = row["binding"]
        _require(type(binding) is dict and set(binding) == _CONTEXT | {"missing"}, "diagnostics_corrupt")
        _require(binding["project_id"] == scope.project_id, "diagnostics_corrupt")
        for name in ("project_id", "component", "operation", "category"):
            _identifier(binding[name])
        for name in ("revision", "branch", "worktree"):
            if binding[name] is not None:
                _sha(binding[name])
        _require(binding["revision"] is not None, "diagnostics_corrupt")
        for name in _FACTS:
            _require(type(binding[name]) is dict and len(binding[name]) <= 32, "diagnostics_corrupt")
            for key, value in binding[name].items():
                _identifier(key)
                _sha(value)
        _require(type(binding["missing"]) is list and len(binding["missing"]) <= 8
                 and all(v in _FACTS + ("revision", "branch", "worktree") for v in binding["missing"]),
                 "diagnostics_corrupt")
        _require(row["bucket"] == _bucket(binding) and row["fingerprint"] == _hash(_json(binding))
                 and row["signature"] == _signature(binding), "diagnostics_corrupt")
        _require(type(row["confidence"]) is str and row["confidence"] in {"unknown", "hypothesis", "confirmed"}
                 and type(row["disposition"]) is str and row["disposition"] in {"advisory", "blocker"}
                 and type(row["status"]) is str and row["status"] in {"open", "resolved", "withdrawn"},
                 "diagnostics_corrupt")
        for name in ("summary", "diagnosis", "resolution"):
            _text(row[name])
        _require(row["confidence"] != "confirmed" or bool(row["diagnosis"].strip()), "diagnostics_corrupt")
        for name in ("created_at", "updated_at"):
            _time(row[name])
        if row["expires_at"] is not None:
            _time(row["expires_at"])
        _sha(row["capture_sha256"])
        _sha(row["origin_sha256"])
        _require(row["parent"] is None if row["revision"] == 1 else type(row["parent"]) is dict,
                 "diagnostics_corrupt")
        if row["parent"] is not None:
            self._reference(scope, row["parent"])
            _require(row["parent"]["case_id"] == row["case_id"] and row["parent"]["bucket"] == row["bucket"]
                     and row["parent"]["revision"] == row["revision"] - 1, "diagnostics_corrupt")
        evidence = row["evidence"]
        _require(type(evidence) is list and 1 <= len(evidence) <= 16, "diagnostics_corrupt")
        for item in evidence:
            _require(type(item) is dict and set(item) == {"revision", "sha256", "original_sha256", "bytes",
                     "original_bytes", "redacted", "truncated", "exact_original"}, "diagnostics_corrupt")
            _sha(item["sha256"])
            _sha(item["original_sha256"])
            _require(type(item["revision"]) is int and 1 <= item["revision"] <= row["revision"], "diagnostics_corrupt")
            _require(type(item["bytes"]) is int and 0 < item["bytes"] <= 1024 * 1024
                     and type(item["original_bytes"]) is int and item["original_bytes"] > 0, "diagnostics_corrupt")
            _require(all(type(item[name]) is bool for name in ("redacted", "truncated", "exact_original")),
                     "diagnostics_corrupt")
            _require(item["exact_original"] == (not item["redacted"] and not item["truncated"]), "diagnostics_corrupt")
        _require(evidence[0]["revision"] == 1 and len({v["revision"] for v in evidence}) == len(evidence),
                 "diagnostics_corrupt")
        for name in ("event", "verification"):
            event = row[name]
            if event is not None:
                _require(type(event) is dict and set(event) == {"kind", "note", "result", "at", "fingerprint"},
                         "diagnostics_corrupt")
                _require(type(event["kind"]) is str
                         and event["kind"] in {"diagnosis", "verification", "resolution", "observation"}
                         and (event["result"] is None or type(event["result"]) is str
                              and event["result"] in {"pass", "fail", "inconclusive"}), "diagnostics_corrupt")
                _text(event["note"])
                _time(event["at"])
                _sha(event["fingerprint"])
        if row["verification"] is not None:
            _require(row["verification"]["kind"] == "verification", "diagnostics_corrupt")
        _require(row["status"] != "resolved" or row["confidence"] == "confirmed"
                 and bool(row["resolution"]) and row["verification"] is not None
                 and row["verification"]["result"] == "pass", "diagnostics_corrupt")
        return row

    def _read_row(self, io, scope, path, ref=None):
        raw = self._read(io, path + "/case.json", limit=65536, control=True)
        ready = _decode(self._read(io, path + "/ready.json", limit=256, control=True))
        _require(type(ready) is dict and set(ready) == {"sha256"}
                 and ready["sha256"] == _hash(raw), "diagnostics_corrupt")
        row = self._validate(_decode(raw), scope)
        _require(raw == _json(row), "diagnostics_corrupt")
        if ref is not None:
            _require(self._ref(row) == ref, "diagnostics_corrupt")
        return row

    def _read(self, io, path, expected=None, *, limit, control=False):
        parts = tuple(path.split("/"))
        parent = io.directory(parts[:-1])
        io._verify_dirs(parts[:-1])
        info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                 and info.st_mode & 0o077 == 0, "diagnostics_permissions")
        return io.read_bytes(path, expected, limit=limit, control=control)

    def _latest(self, io, scope, base):
        names = self._names(io, base, 256)
        _require(bool(names), "diagnostics_not_found")
        _require(all(_REV.fullmatch(name) for name in names)
                 and names == [f"r{n:08d}" for n in range(1, len(names) + 1)], "diagnostics_corrupt")
        row = self._read_row(io, scope, base + "/" + names[-1])
        _require(row["revision"] == len(names) and base.endswith('/' + row["bucket"] + '/' + row["case_id"]),
                 "diagnostics_corrupt")
        return row

    def _evidence(self, raw, revision, secrets):
        _require(type(raw) is bytes and 0 < len(raw) <= 1024 * 1024, "diagnostics_evidence_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            raise DiagnosticsError("diagnostics_evidence_utf8_required") from None
        clean = _redact(text, secrets).encode("utf-8")
        retained = clean[:self.limits.max_evidence_bytes].decode("utf-8", errors="ignore").encode("utf-8")
        _require(bool(retained), "diagnostics_evidence_limit")
        truncated = len(retained) != len(clean)
        return retained, {"revision": revision, "sha256": _hash(retained), "original_sha256": _hash(raw),
                          "bytes": len(retained), "original_bytes": len(raw), "redacted": clean != raw,
                          "truncated": truncated, "exact_original": clean == raw and not truncated}

    def _health(self, io, project, row):
        base = f'{project}/buckets/{row["bucket"]}/{row["case_id"]}'
        for evidence in row["evidence"]:
            path = f'{base}/r{evidence["revision"]:08d}/evidence.bin'
            raw = self._read(io, path, evidence["sha256"], limit=self.limits.max_evidence_bytes)
            _require(len(raw) == evidence["bytes"], "diagnostics_corrupt")

    def _pending_names(self, io, project):
        names = self._names(io, project + "/pending", 64)
        _require(all(re.fullmatch(r"[pd]-[0-9a-f]{32}", name) for name in names), "diagnostics_corrupt")
        return names

    def _intent(self, io, scope, path):
        if path.rsplit("/", 1)[-1].startswith("d-"):
            ref = _decode(self._read(io, path + "/prune.json", limit=4096, control=True))
            self._reference(scope, ref)
            return {key: ref[key] for key in ("bucket", "case_id", "revision")}
        value = _decode(self._read(io, path + "/intent.json", limit=4096, control=True))
        _require(type(value) is dict and set(value) == {"bucket", "case_id", "revision", "parent"}, "diagnostics_corrupt")
        _sha(value["bucket"])
        _identifier(value["case_id"])
        _require(type(value["revision"]) is int and 1 <= value["revision"] <= 256, "diagnostics_corrupt")
        if value["parent"] is not None:
            self._reference(scope, value["parent"])
        return value

    def _no_pending(self, io, scope, project, bucket, case_id):
        for name in self._pending_names(io, project):
            intent = self._intent(io, scope, project + "/pending/" + name)
            _require((intent["bucket"], intent["case_id"]) != (bucket, case_id), "diagnostics_recovery_required")

    def _commit(self, io, scope, project, row, evidence):
        self._no_pending(io, scope, project, row["bucket"], row["case_id"])
        total, cases = self._inventory(io, project)
        names = self._pending_names(io, project)
        raw = _json(row)
        _require(len(raw) <= 65536, "diagnostics_capacity")
        _require(row["revision"] <= self.limits.max_revisions
                 and (row["revision"] != 1 or cases < self.limits.max_cases)
                 and len(names) < self.limits.max_pending
                 and total + len(raw) + len(evidence or b"") + 8192 <= self.limits.max_total_bytes,
                 "diagnostics_capacity")
        io.mkdir(project + "/pending")
        stage = project + "/pending/p-" + uuid.uuid4().hex
        io.mkdir(stage, exclusive=True)
        intent = {key: row[key] for key in ("bucket", "case_id", "revision", "parent")}
        io.write_new(stage + "/intent.json", _json(intent))
        self.fault("intent")
        if evidence is not None:
            io.write_new(stage + "/evidence.bin", evidence)
        self.fault("evidence")
        io.write_new(stage + "/case.json", raw)
        io.write_new(stage + "/ready.json", _json({"sha256": _hash(raw)}))
        os.fsync(io.directory(tuple(stage.split("/"))))
        self.fault("ready")
        self._publish(io, scope, project, stage, row)
        self.fault("published")
        return self._ref(row)

    def _publish(self, io, scope, project, stage, row):
        base = f'{project}/buckets/{row["bucket"]}/{row["case_id"]}'
        if row["revision"] == 1:
            _require(not self._names(io, base, 256), "diagnostics_conflict")
            _, cases = self._inventory(io, project)
            _require(cases < self.limits.max_cases, "diagnostics_capacity")
        else:
            _require(self._ref(self._latest(io, scope, base)) == row["parent"], "diagnostics_conflict")
        _require(row["revision"] <= self.limits.max_revisions, "diagnostics_capacity")
        io.mkdir(base)
        parent = io.directory(tuple(base.split("/")))
        source = io.directory(tuple((project + "/pending").split("/")))
        io._verify_dirs(tuple(base.split("/")))
        io._verify_dirs(tuple(stage.split("/")))
        target = f'r{row["revision"]:08d}'
        _require(target not in os.listdir(parent), "diagnostics_conflict")
        self._verify(scope, write=True)
        os.rename(stage.rsplit("/", 1)[-1], target, src_dir_fd=source, dst_dir_fd=parent)
        io.diagnostics_published = True
        for path in (base, base.rsplit("/", 1)[0], project + "/buckets", project + "/pending",
                     project, "diagnostics/v1", "diagnostics"):
            os.fsync(io.directory(tuple(path.split("/"))))
        os.fsync(io.directory(()))

    def capture(self, scope, *, case_id, context, evidence, summary="", confidence="unknown",
                disposition="advisory", diagnosis="", expires_at=None, origin=None, secrets=()):
        self._verify(scope, write=True)
        case_id = _identifier(case_id)
        secrets = _secrets(secrets)
        binding = _binding(context, capture=True, secrets=secrets)
        _require(binding["project_id"] == scope.project_id, "not_available")
        retained, descriptor = self._evidence(evidence, 1, secrets)
        _require(origin is None or type(origin) is dict and len(_json(origin)) <= 8192)
        if origin is not None:
            for key, value in origin.items():
                _identifier(key)
                _require(not re.search(r"(?i)password|passwd|secret|token|api_key|credential", key),
                         "diagnostics_sensitive_context")
                _text(value, 1024)
                _require(_redact(value, secrets) == value, "diagnostics_sensitive_context")
        stamp = self.clock()
        _time(stamp)
        row = {"contract": CONTRACT, "project_id": scope.project_id, "bucket": _bucket(binding),
               "case_id": case_id, "revision": 1, "parent": None, "created_at": stamp,
               "updated_at": stamp, "binding": binding, "signature": _signature(binding),
               "fingerprint": _hash(_json(binding)), "summary": _redact(_text(summary), secrets),
               "confidence": confidence, "disposition": disposition, "status": "open",
               "diagnosis": _redact(_text(diagnosis), secrets), "resolution": "", "event": None,
               "verification": None, "expires_at": expires_at, "evidence": [descriptor],
               "capture_sha256": "0" * 64, "origin_sha256": _hash(_json(origin))}
        row["capture_sha256"] = _hash(_json({k: v for k, v in row.items()
                                           if k not in {"created_at", "updated_at", "capture_sha256"}}))
        self._validate(row, scope)
        with self._session(scope, write=True) as (io, project):
            base = f'{project}/buckets/{row["bucket"]}/{case_id}'
            if self._names(io, base, 256):
                first = self._read_row(io, scope, base + "/r00000001")
                _require(first["capture_sha256"] == row["capture_sha256"], "diagnostics_conflict")
                self._health(io, project, first)
                return {"status": "existing", "ref": self._ref(first), "evidence": first["evidence"]}
            ref = self._commit(io, scope, project, row, retained)
            return {"status": "created", "ref": ref, "evidence": row["evidence"]}

    def revise(self, scope, ref, *, confidence=None, disposition=None, status=None, diagnosis=None,
               resolution=None, summary=None, expires_at=UNSET, context=None, evidence=None,
               event=None, secrets=()):
        self._verify(scope, write=True)
        base = self._reference(scope, ref)
        secrets = _secrets(secrets)
        with self._session(scope, write=True) as (io, project):
            previous = self._latest(io, scope, base)
            _require(self._ref(previous) == ref, "diagnostics_conflict")
            try:
                self._health(io, project, previous)
            except (OSError, ValueError):
                # Withdrawing reliance remains possible when its evidence is
                # damaged. It makes no claim of a fix or successful verification.
                if status != "withdrawn":
                    raise
            row = _decode(_json(previous))
            row.update(revision=previous["revision"] + 1, parent=dict(ref), updated_at=self.clock(), event=None)
            retained = None
            if context is not None:
                binding = _binding(context, capture=True, secrets=secrets)
                _require(binding["project_id"] == scope.project_id and _bucket(binding) == row["bucket"],
                         "diagnostics_scope_conflict")
                if binding != row["binding"]:
                    _require(evidence is not None, "diagnostics_new_evidence_required")
                    row.update(binding=binding, fingerprint=_hash(_json(binding)), signature=_signature(binding),
                               confidence="unknown", verification=None, status="open", resolution="")
            for name, value in (("confidence", confidence), ("disposition", disposition), ("status", status)):
                if value is not None:
                    row[name] = value
            for name, value in (("diagnosis", diagnosis), ("resolution", resolution), ("summary", summary)):
                if value is not None:
                    row[name] = _redact(_text(value), secrets)
            if expires_at is not UNSET:
                row["expires_at"] = expires_at
            if evidence is not None:
                retained, descriptor = self._evidence(evidence, row["revision"], secrets)
                duplicate = any(all(old[key] == descriptor[key] for key in descriptor if key != "revision")
                                for old in row["evidence"])
                if duplicate:
                    retained = None
                else:
                    _require(len(row["evidence"]) < 16, "diagnostics_capacity")
                    row["evidence"].append(descriptor)
                row["verification"] = None
                if previous["status"] == "resolved":
                    if status is None:
                        row["status"] = "open"
                    if resolution is None:
                        row["resolution"] = ""
            if event is not None:
                _require(type(event) is dict and set(event) == {"kind", "note", "result"})
                row["event"] = {**event, "note": _redact(_text(event["note"]), secrets),
                                "at": row["updated_at"], "fingerprint": row["fingerprint"]}
                if event["kind"] == "verification":
                    row["verification"] = row["event"]
            self._validate(row, scope)
            result = self._commit(io, scope, project, row, retained)
            return {"status": "revised", "ref": result, "evidence": row["evidence"]}

    def _summary(self, row):
        # User-provided observation/diagnosis prose stays out of ordinary lookup.
        return {"ref": self._ref(row), "component": row["binding"]["component"],
                "operation": row["binding"]["operation"], "category": row["binding"]["category"],
                "signature": row["signature"], "fingerprint": row["fingerprint"],
                "confidence": row["confidence"], "disposition": row["disposition"], "status": row["status"],
                "expires_at": row["expires_at"], "summary": "Locally retained diagnostic case."}

    def _page(self, *, limit, byte_limit):
        _require(type(limit) is int and 1 <= limit <= 50)
        _require(type(byte_limit) is int and 2048 <= byte_limit <= 1024 * 1024, "diagnostics_output_limit")

    def _fit(self, result, byte_limit):
        _require(len(_json(result)) <= byte_limit, "diagnostics_output_limit")
        return result

    def show(self, scope, ref, *, include_evidence=False, byte_limit=32768):
        self._page(limit=1, byte_limit=byte_limit)
        _require(type(include_evidence) is bool)
        self._verify(scope)
        base = self._reference(scope, ref)
        with self._session(scope) as (io, project):
            row = self._read_row(io, scope, f'{base}/r{ref["revision"]:08d}', ref)
            self._health(io, project, row)
            result = {"contract": CONTRACT, "case": self._summary(row), "evidence": row["evidence"],
                      "binding": row["binding"], "parent": row["parent"], "event": None,
                      "diagnosis": {"confidence": row["confidence"], "summary": "Available by explicit evidence read."}}
            if include_evidence:
                result.update(summary=row["summary"], diagnosis={"confidence": row["confidence"], "summary": row["diagnosis"]},
                              resolution=row["resolution"], event=row["event"])
                contents = []
                for item in row["evidence"]:
                    raw = self._read(io, f'{base}/r{item["revision"]:08d}/evidence.bin', item["sha256"],
                                     limit=self.limits.max_evidence_bytes)
                    contents.append({"revision": item["revision"], "text": raw.decode("utf-8"),
                                     "exact_original": item["exact_original"]})
                result["contents"] = contents
            return self._fit(result, byte_limit)

    def read_evidence(self, scope, ref, *, evidence_revision=1, offset=0, byte_limit=32768):
        """Explicit bounded byte ranges of one retained artifact, base64 encoded."""
        self._page(limit=1, byte_limit=byte_limit)
        self._verify(scope)
        base = self._reference(scope, ref)
        _require(type(evidence_revision) is int and 1 <= evidence_revision <= ref["revision"])
        _require(type(offset) is int and 0 <= offset <= self.limits.max_evidence_bytes)
        with self._session(scope) as (io, project):
            row = self._read_row(io, scope, f'{base}/r{ref["revision"]:08d}', ref)
            selected = [item for item in row["evidence"] if item["revision"] == evidence_revision]
            _require(len(selected) == 1, "diagnostics_not_found")
            item = selected[0]
            raw = self._read(io, f'{base}/r{evidence_revision:08d}/evidence.bin', item["sha256"],
                             limit=self.limits.max_evidence_bytes)
            _require(len(raw) == item["bytes"] and offset <= len(raw), "diagnostics_invalid_request")
            count = ((byte_limit - 1536) // 4) * 3
            end = min(len(raw), offset + count)
            result = {"contract": CONTRACT, "ref": dict(ref), "evidence": item, "offset": offset,
                      "end": end, "next_offset": end if end < len(raw) else None,
                      "body_base64": base64.b64encode(raw[offset:end]).decode("ascii")}
            return self._fit(result, byte_limit)

    def _candidates(self, io, project, binding):
        base = project + "/buckets/" + _bucket(binding)
        names = self._names(io, base, 4096)
        _require(all(_ID.fullmatch(name) for name in names), "diagnostics_corrupt")
        return base, names

    def _invalid(self, row, binding, stamp):
        reasons = []
        saved = row["binding"]
        for name in ("revision",) + _FACTS:
            if saved[name] != binding[name]:
                reasons.append(name + "_changed")
        for name in ("branch", "worktree"):
            if saved[name] is not None and saved[name] != binding[name]:
                reasons.append(name + "_changed")
        if saved["missing"] or binding["missing"]:
            reasons.append("relevant_conditions_unproven")
        if row["expires_at"] is None:
            reasons.append("expiry_unbounded")
        elif _time(row["expires_at"]) <= stamp:
            reasons.append("expired")
        if row["status"] == "withdrawn":
            reasons.append("withdrawn")
        if row["confidence"] != "confirmed":
            reasons.append("cause_unconfirmed")
        if any(item["truncated"] for item in row["evidence"]):
            reasons.append("evidence_truncated")
        return reasons

    def preflight(self, scope, context, *, cursor=None, limit=20, byte_limit=32768):
        self._page(limit=limit, byte_limit=byte_limit)
        self._verify(scope)
        binding = _binding(context, capture=False)
        _require(binding["project_id"] == scope.project_id, "not_available")
        if cursor is not None:
            _identifier(cursor)
        result = {"contract": CONTRACT, "blocking": False, "matches": [], "next_cursor": None,
                  "coverage": "complete", "warnings": [], "scanned": 0,
                  "history": "present", "skipped_checks": [], "retry_authorized": False}
        try:
            with self._session(scope, allow_absent=True) as (io, project):
                if project is None:
                    result["history"] = "absent"
                    names, pending, base = [], [], None
                else:
                    base, names = self._candidates(io, project, binding)
                    pending = self._pending_names(io, project)
                if pending:
                    result["warnings"].append("diagnostics_pending_recovery")
                    result["coverage"] = "degraded"
                _require(len(names) <= self.limits.max_scan, "diagnostics_scan_limit")
                eligible = []
                stamp = _time(self.clock())
                for name in names:
                    row = self._latest(io, scope, base + "/" + name)
                    result["scanned"] += 1
                    if binding["category"] is not None and row["binding"]["category"] != binding["category"]:
                        continue
                    reasons = self._invalid(row, binding, stamp)
                    try:
                        self._health(io, project, row)
                    except (OSError, ValueError):
                        reasons.append("evidence_missing_or_changed")
                        result["coverage"] = "degraded"
                    reusable = not reasons
                    blocker = reusable and row["disposition"] == "blocker" and row["status"] == "open"
                    result["blocking"] = result["blocking"] or blocker
                    if cursor is None or name > cursor:
                        match = self._summary(row)
                        match.update(blocking=blocker, reusable=reusable, invalidation=reasons,
                                     optional_verification_reusable=reusable and row["verification"] is not None
                                     and row["verification"]["fingerprint"] == row["fingerprint"]
                                     and row["verification"]["result"] in {"pass", "fail"})
                        eligible.append(match)
                for match in eligible:
                    candidate = {**result, "matches": result["matches"] + [match]}
                    if len(result["matches"]) >= limit or len(_json(candidate)) + 128 > byte_limit:
                        result["next_cursor"] = result["matches"][-1]["ref"]["case_id"] if result["matches"] else cursor
                        _require(bool(result["matches"]), "diagnostics_output_limit")
                        break
                    result["matches"].append(match)
        except DiagnosticsError as exc:
            if exc.code in _AUTHORITY:
                raise
            result["coverage"] = "degraded"
            result["history"] = "unavailable"
            result["warnings"].append(exc.code)
        result["decision"] = ("blocked" if result["blocking"] else "reduced_coverage"
                              if result["coverage"] != "complete" else "advisory"
                              if result["matches"] else "clear")
        # No hidden raw exception message, filesystem name or operation detail.
        return self._fit(result, byte_limit)

    def query(self, scope, *, component, operation, cursor=None, limit=20, byte_limit=32768):
        self._page(limit=limit, byte_limit=byte_limit)
        self._verify(scope)
        binding = {"component": _identifier(component), "operation": _identifier(operation)}
        if cursor is not None:
            _identifier(cursor)
        with self._session(scope) as (io, project):
            base, names = self._candidates(io, project, binding)
            names = [name for name in names if cursor is None or name > cursor]
            result = {"contract": CONTRACT, "items": [], "next_cursor": None}
            for name in names:
                row = self._latest(io, scope, base + "/" + name)
                candidate = {**result, "items": result["items"] + [self._summary(row)]}
                if len(result["items"]) >= limit or len(_json(candidate)) + 128 > byte_limit:
                    _require(bool(result["items"]), "diagnostics_output_limit")
                    result["next_cursor"] = result["items"][-1]["ref"]["case_id"]
                    break
                result["items"].append(self._summary(row))
            return self._fit(result, byte_limit)

    def pending(self, scope):
        self._verify(scope)
        with self._session(scope) as (io, project):
            result = []
            for name in self._pending_names(io, project):
                state = "incomplete"
                try:
                    if name.startswith("d-"):
                        self._intent(io, scope, project + "/pending/" + name)
                        state = "retention"
                    else:
                        self._ready(io, scope, project, project + "/pending/" + name)
                        state = "ready"
                except (OSError, ValueError):
                    pass
                result.append({"pending_id": name, "state": state})
            return {"contract": CONTRACT, "items": result}

    def _ready(self, io, scope, project, path):
        intent = self._intent(io, scope, path)
        ready = _decode(self._read(io, path + "/ready.json", limit=256, control=True))
        _require(type(ready) is dict and set(ready) == {"sha256"}, "diagnostics_corrupt")
        row = self._read_row(io, scope, path)
        _require(_hash(_json(row)) == ready["sha256"]
                 and {key: row[key] for key in intent} == intent, "diagnostics_corrupt")
        for item in row["evidence"]:
            source = path if item["revision"] == row["revision"] else (
                f'{project}/buckets/{row["bucket"]}/{row["case_id"]}/r{item["revision"]:08d}')
            raw = self._read(io, source + "/evidence.bin", item["sha256"], limit=self.limits.max_evidence_bytes)
            _require(len(raw) == item["bytes"], "diagnostics_corrupt")
        return row

    def _remove(self, io, path, depth=0):
        _require(depth < 5, "diagnostics_corrupt")
        parts = tuple(path.split("/"))
        fd = io.directory(parts)
        names = os.listdir(fd)
        _require(len(names) <= 256, "diagnostics_capacity")
        for name in names:
            io.budget.tick()
            io._verify_dirs(parts)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                self._remove(io, path + "/" + name, depth + 1)
            else:
                _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "diagnostics_corrupt")
                os.unlink(name, dir_fd=fd)
        io._verify_dirs(parts)
        parent = io.directory(parts[:-1])
        os.rmdir(parts[-1], dir_fd=parent)
        os.fsync(parent)

    def recover(self, scope, pending_id, *, action="publish"):
        self._verify(scope, write=True)
        _require(type(pending_id) is str and re.fullmatch(r"[pd]-[0-9a-f]{32}", pending_id))
        _require(action in {"publish", "discard"})
        with self._session(scope, write=True) as (io, project):
            path = project + "/pending/" + pending_id
            if pending_id.startswith("d-"):
                if action == "discard":
                    # Retention was already explicitly authorized. Discard may
                    # remove its detached withdrawn bytes, never the live case.
                    self._remove(io, path)
                    return {"status": "discarded", "pending_id": pending_id}
                return self._finish_prune(io, scope, project, path)
            if action == "discard":
                self._remove(io, path)
                return {"status": "discarded", "pending_id": pending_id}
            row = self._ready(io, scope, project, path)
            self._publish(io, scope, project, path, row)
            return {"status": "recovered", "ref": self._ref(row)}

    def prune(self, scope, ref):
        self._verify(scope, write=True)
        base = self._reference(scope, ref)
        with self._session(scope, write=True) as (io, project):
            row = self._latest(io, scope, base)
            _require(self._ref(row) == ref, "diagnostics_conflict")
            _require(row["status"] == "withdrawn", "diagnostics_retention_protected")
            self._no_pending(io, scope, project, row["bucket"], row["case_id"])
            _require(len(self._pending_names(io, project)) < self.limits.max_pending, "diagnostics_capacity")
            io.mkdir(project + "/pending")
            stage = project + "/pending/d-" + uuid.uuid4().hex
            io.mkdir(stage, exclusive=True)
            io.write_new(stage + "/prune.json", _json(ref))
            os.fsync(io.directory(tuple(stage.split("/"))))
            os.fsync(io.directory(tuple((project + "/pending").split("/"))))
            self.fault("prune_reserved")
            return self._finish_prune(io, scope, project, stage)

    def _finish_prune(self, io, scope, project, stage):
        ref = _decode(self._read(io, stage + "/prune.json", limit=4096, control=True))
        base = self._reference(scope, ref)
        stage_parts = tuple(stage.split("/"))
        stage_fd = io.directory(stage_parts)
        try:
            info = os.stat("case", dir_fd=stage_fd, follow_symlinks=False)
            _require(stat.S_ISDIR(info.st_mode), "diagnostics_corrupt")
            detached = True
        except FileNotFoundError:
            detached = False
        if not detached and self._names(io, base, 256):
            row = self._latest(io, scope, base)
            _require(self._ref(row) == ref, "diagnostics_conflict")
            _require(row["status"] == "withdrawn", "diagnostics_retention_protected")
            parts = tuple(base.split("/"))
            source = io.directory(parts[:-1])
            io._verify_dirs(parts)
            io._verify_dirs(stage_parts)
            self._verify(scope, write=True)
            os.rename(parts[-1], "case", src_dir_fd=source, dst_dir_fd=stage_fd)
            io.diagnostics_published = True
            os.fsync(source)
            os.fsync(stage_fd)
            detached = True
            self.fault("prune_detached")
        if detached:
            # Read the detached tree through newly authenticated handles; the
            # previous case's open handles no longer name the live namespace.
            self._remove(io, stage + "/case")
            self.fault("prune_cleaned")
        self._remove(io, stage)
        return {"status": "pruned", "case_id": ref["case_id"]}

    def capture_failure(self, scope, *, primary_code, **arguments):
        # The original error is owned by the action caller. Never replace it
        # with optional diagnostic capacity/storage failure or its raw message.
        _identifier(primary_code)
        try:
            return {"primary_code": primary_code, "capture": self.capture(scope, **arguments), "warnings": []}
        except DiagnosticsError as exc:
            if exc.code in _AUTHORITY:
                raise
            return {"primary_code": primary_code, "capture": None, "warnings": [exc.code],
                    "next_action": exc.next_action}


def owner_diagnostics(project, *, write=False):
    """Explicit owner linkage through the existing configured user data root."""
    from .records.application import owner_store
    store, scope = owner_store(project, write=write)
    return DiagnosticStore(store.root), scope
