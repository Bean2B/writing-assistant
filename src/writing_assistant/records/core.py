"""Creative Records v1: immutable originals in an explicitly authorized data root.

This library neither discovers host authority nor imports optional product modules.
The caller owns authorization. See docs/records.md.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

from . import safeio as _record_io
from .safeio import Budget
from .bounded_io import RecordSession as SafeSession

CONTRACT = "creative-records/1"
BODY_LIMIT = 16 * 1024 * 1024
META_LIMIT = 1024 * 1024
QUERY_NAMESPACE_LIMIT = 10000
KINDS = frozenset({"idea", "fragment", "draft", "setting", "decision", "feedback", "prose"})
AUTHORSHIP = frozenset({"user", "agent", "mixed", "unknown"})
_IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}")
_SHA_RE = re.compile(r"[0-9a-f]{64}")


class RecordsError(ValueError):
    """Stable, payload-free public diagnostic."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code="invalid_request"):
    if not condition:
        raise RecordsError(code)


def identifier(value):
    require(isinstance(value, str) and _IDENTIFIER_RE.fullmatch(value), "invalid_identifier")
    return value


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise RecordsError("invalid_request") from None


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "corrupt_record")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, "corrupt_record"))
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError):
        raise RecordsError("corrupt_record") from None


def keys(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()), "invalid_schema")


def sha(value):
    require(isinstance(value, str) and _SHA_RE.fullmatch(value), "invalid_digest")
    return value


def timestamp(value, *, nullable=False):
    if nullable and value is None:
        return
    require(isinstance(value, str) and len(value) <= 128, "corrupt_record")
    try:
        parsed = datetime.fromisoformat(value)
        require(parsed.tzinfo is not None, "corrupt_record")
    except ValueError:
        raise RecordsError("corrupt_record") from None


def ref_key(ref):
    keys(ref, "contract project_id record_id version_id sha256")
    require(ref["contract"] == CONTRACT, "unsupported_version")
    for name in ("project_id", "record_id", "version_id"):
        identifier(ref[name])
    sha(ref["sha256"])
    return ref["version_id"]


@dataclass(frozen=True)
class Scope:
    """Caller-supplied scope, not a grant or a deserializable authority token.

    `check` must raise when the caller's current authority has expired. It runs
    before I/O and before return, including cached/navigation operations.
    A local data-owner application may explicitly provide a no-op callback.
    """
    project_id: str
    audience: str
    check: object
    writable: bool = False
    record_ids: frozenset | None = None

    def verify(self, record_id=None, *, write=False):
        identifier(self.project_id)
        identifier(self.audience)
        require(callable(self.check), "authority_required")
        require(not write or self.writable, "not_available")
        require(self.record_ids is None or isinstance(self.record_ids, frozenset), "invalid_scope")
        if record_id is not None:
            identifier(record_id)
            require(self.record_ids is None or record_id in self.record_ids, "not_available")
        try:
            self.check()
        except Exception:
            # A callback's exception/code is untrusted application detail.
            # Keep global authority failure distinct from a filtered record.
            # BaseException control flow (interrupt/exit) must still propagate.
            raise RecordsError("authority_failed") from None


class _RecordIO(SafeSession):
    """Open a new leaf directly from its authenticated, already held parent."""

    def _register(self, path, handle):
        if os.name != "posix":
            return super()._register(path, handle)
        super()._register(path, handle)
        # Cache only the immutable absolute spelling, never native state.
        path, handle, identity = self._anchors[-1]
        self._anchors[-1] = (str(path), handle, identity)

    def _verify_dirs(self, parts=None):
        # RecordStore is POSIX-only and pinned to this SafeSession contract.
        # Preserve every native check and its ordering; directory verification
        # needs identity/type, not the file size/timestamps built by _state.
        if os.name != "posix":
            return super()._verify_dirs(parts)
        self.budget.tick()
        anchors = self._anchors if parts is None else list(self._root_anchors) + [
            self._dir_anchors[tuple(parts[:index])]
            for index in range(1, len(parts) + 1) if tuple(parts[:index]) in self._dir_anchors]
        for path, handle, identity in anchors:
            row = os.fstat(handle)
            if not stat.S_ISDIR(row.st_mode):
                raise ValueError("local I/O requires ordinary single-link files")
            if (row.st_dev, row.st_ino) != identity:
                raise ValueError("held directory identity changed")
            row = os.stat(path, follow_symlinks=False)
            if not stat.S_ISDIR(row.st_mode) or (row.st_dev, row.st_ino) != identity:
                raise ValueError("POSIX ancestor namespace changed")

    def directory(self, parts, *, create=False, exclusive=False):
        key = tuple(parts)
        parent = key[:-1]
        version_lookup = (len(key) == 4 and key[0] == "projects" and key[2] == "versions"
                          and not create and not exclusive)
        if version_lookup:
            # Every version-directory consumer verifies the complete chain
            # before content open, listing, write or sync. Coalesce the adjacent
            # parent-only check into that check, without caching native state.
            self.budget.tick()
            if key in self._dirs:
                return self._dirs[key]
        if not key or create or exclusive or key in self._dirs or parent not in self._dirs:
            return super().directory(parts, create=create, exclusive=exclusive)
        if not version_lookup:
            self._verify_dirs(parent)
        handle = os.open(key[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self._dirs[parent])
        self._register(self.root.joinpath(*key), handle)
        self._dir_anchors[key] = self._anchors[-1]
        self._dirs[key] = handle
        return handle

    def read_inline_body(self, path, *, expected_sha256, expected_size, verify):
        """Read a metadata-bound inline body under coherent file-size semantics.

        This is not the generic reader or an authorization source. Its caller
        has validated the envelope, exact reference, length and digest. Keep
        the original reader when the initial native length differs.
        """
        parts = _record_io.relative_name(self.root, path)
        version = parts[:-1]
        if (os.name != "posix" or len(parts) != 5 or parts[0] != "projects"
                or parts[2] != "versions" or parts[-1] != "body.bin"):
            raw = self.read_bytes(path, expected_sha256=expected_sha256)
            verify()
            return raw
        primary_error = None
        try:
            parent = self.directory(version)
            self._verify_dirs(version)
            handle = _record_io._open_child(parent, parts[-1])
            read_error = None
            try:
                logical = self.root.joinpath(*parts)
                initial = _record_io._state(handle, logical, False)
                size = initial[1]
                if size == expected_size:
                    limit = self.budget.file_bytes
                    if size > limit:
                        raise ValueError("local I/O file exceeds byte limit")
                    expected = expected_sha256.lower()
                    self.budget.reserve("/".join(parts), expected, size, False)
                    hasher, raw, total = hashlib.sha256(), bytearray(), 0
                    while total < size:
                        self._verify_dirs(version)
                        if _record_io._state(handle, logical, False) != initial:
                            raise ValueError("input identity or metadata changed during read")
                        block = _record_io._read_chunk(handle, min(_record_io.CHUNK, limit - total + 1))
                        self.budget.consume(len(block))
                        if not block:
                            break
                        total += len(block)
                        if total > limit or total > size:
                            raise ValueError("input grew beyond authenticated size")
                        hasher.update(block)
                        raw.extend(block)
                    if total != size or _record_io._state(handle, logical, False) != initial:
                        raise ValueError("input was truncated or changed")
                    if hasher.hexdigest() != expected:
                        raise _record_io.HashMismatch("input SHA-256 differs from declared version")
                    raw = bytes(raw)
            except BaseException as error:
                read_error = error
                raise
            finally:
                try:
                    _record_io._close(handle)
                except BaseException as error:
                    if (read_error is None or isinstance(read_error, Exception)
                            and not isinstance(error, Exception)):
                        raise
            if size != expected_size:
                # Preserve the original EOF/limit/hash behavior and its error
                # priority; the metadata length is not a new early rejection.
                raw = _record_io.SafeSession._read(
                    self, path, expected_sha256, self.budget.file_bytes, True, False)
            verify()  # File is closed; live authority before leaf release.
            return raw
        except BaseException as error:
            primary_error = error
            raise
        finally:
            cleanup_error = None
            if version in self._dirs:
                try:
                    # This also checks the completion deadline. A project-only
                    # session-exit check cannot replace the held version chain.
                    self._verify_dirs(version)
                except BaseException as error:
                    cleanup_error = error
                try:
                    anchor = self._dir_anchors.pop(version)
                    self._anchors.remove(anchor)
                    del self._dirs[version]
                    os.close(anchor[1])
                except BaseException as error:
                    if (cleanup_error is None or isinstance(cleanup_error, Exception)
                            and not isinstance(error, Exception)):
                        cleanup_error = error
            if (cleanup_error is not None and (primary_error is None
                    or isinstance(primary_error, Exception) and not isinstance(cleanup_error, Exception))):
                raise cleanup_error



class RecordStore:
    """POSIX component; root must already exist and be authorized by its caller.

    Each complete version is a directory atomically renamed from private staging
    under a per-project advisory lock. Crashed staging is preserved, not inferred
    to be complete. Locks require cooperative clients and a stable namespace;
    this is not an OS sandbox against another process with the same OS identity.
    """

    def __init__(self, root, *, resolver=None, fault=None):
        self.root = Path(root)
        self.resolver = resolver
        self.fault = fault or (lambda stage: None)

    @contextmanager
    def session(self, scope, *, write=False, record_id=None):
        scope.verify(record_id, write=write)
        require(os.name == "posix", "unsupported_platform")
        io = None
        try:
            with _RecordIO(self.root, Budget(file_bytes=BODY_LIMIT, input_bytes=512 * 1024 * 1024,
                                              read_bytes=1024 * 1024 * 1024, seconds=120)) as io:
                io._records_published = False
                try:
                    yield io
                    scope.verify(record_id, write=write)
                    io._verify_dirs(tuple(self.project(scope).split("/")))
                except (OSError, ValueError):
                    if write and io._records_published:
                        raise RecordsError("outcome_unknown") from None
                    raise
        except RecordsError:
            raise
        except FileNotFoundError:
            if write and io is not None and io._records_published:
                raise RecordsError("outcome_unknown") from None
            raise RecordsError("not_available") from None
        except (OSError, ValueError):
            if write and io is not None and io._records_published:
                raise RecordsError("outcome_unknown") from None
            raise RecordsError("storage_error") from None

    def project(self, scope):
        return "projects/" + identifier(scope.project_id)

    def _sync(self, io, relative):
        fd = io.directory(tuple(relative.split("/")))
        io._verify_dirs(tuple(relative.split("/")))
        os.fsync(fd)

    @contextmanager
    def lock(self, io, scope):
        import fcntl
        project = self.project(scope)
        io.mkdir(project)
        parts = tuple(project.split("/"))
        parent = io.directory(parts)
        io._verify_dirs(parts)
        fd = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        try:
            row = os.fstat(fd)
            require(stat.S_ISREG(row.st_mode) and row.st_nlink == 1, "storage_error")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RecordsError("busy") from None
            io._verify_dirs(parts)
            current = os.stat(".lock", dir_fd=parent, follow_symlinks=False)
            require((row.st_dev, row.st_ino) == (current.st_dev, current.st_ino), "storage_error")
            scope.verify(write=True)
            yield project
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _directories(self, io, path):
        try:
            fd = io.directory(tuple(path.split("/")))
        except FileNotFoundError:
            return []
        result = []
        for name in sorted(os.listdir(fd)):
            identifier(name)
            row = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(stat.S_ISDIR(row.st_mode), "corrupt_record")
            result.append(name)
        return result

    def _query_versions(self, io, scope):
        """Enumerate a capped navigation namespace without opening every source.

        Canonical metadata and bodies are validated only when selected. The
        original flat layout needs an O(N) name pass for deterministic ordering;
        refuse at the cap rather than allocating an unbounded listdir result.
        """
        parts = tuple((self.project(scope) + "/versions").split("/"))
        try:
            fd = io.directory(parts)
        except FileNotFoundError:
            return [], None
        io._verify_dirs(parts)
        before = os.fstat(fd)
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                io.budget.tick()
                require(len(names) < QUERY_NAMESPACE_LIMIT, "scan_limit_exceeded")
                names.append(identifier(entry.name))
        after = os.fstat(fd)
        generation = lambda row: (row.st_dev, row.st_ino, row.st_mtime_ns, row.st_ctime_ns)
        require(generation(before) == generation(after), "stale_cursor")
        io._verify_dirs(parts)
        return sorted(names), generation(after)

    def _verify_query_generation(self, io, scope, generation):
        parts = tuple((self.project(scope) + "/versions").split("/"))
        try:
            fd = io.directory(parts)
        except FileNotFoundError:
            require(generation is None, "stale_cursor")
            return
        io._verify_dirs(parts)
        row = os.fstat(fd)
        require(generation == (row.st_dev, row.st_ino, row.st_mtime_ns, row.st_ctime_ns),
                "stale_cursor")

    def _release_leaf(self, io, path):
        """Bound SafeSession's pinned-directory set during version scans.

        This component is pinned to the existing SafeSession implementation.
        Only a fully read leaf with no active file handle is released.
        """
        key = tuple(path.split("/"))
        anchor = io._dir_anchors.pop(key, None)
        if anchor is not None:
            io._anchors.remove(anchor)
            del io._dirs[key]
            os.close(anchor[1])

    def _record_route(self, io, scope, version_id, *, required=True):
        """Canonical identity namespace, not the disposable query index.

        New versions publish this empty directory with their original files.
        Legacy versions require an explicit full-owner binding operation.
        No foreign record envelope is opened to discover its identity.
        """
        path = self.project(scope) + "/versions/" + identifier(version_id) + "/identity"
        record_path = None
        try:
            names = self._directories(io, path)
            if not names and not required:
                return None
            require(len(names) == 1 and re.fullmatch(r"r-[0-9a-f]{64}", names[0]), "routing_unavailable")
            record_path = path + "/" + names[0]
            binding = "k-" + digest(encoded([scope.project_id, version_id, names[0]]))
            require(self._directories(io, record_path) == [binding], "routing_unavailable")
            return names[0]
        except (OSError, ValueError):
            raise RecordsError("routing_unavailable") from None
        finally:
            if record_path is not None:
                self._release_leaf(io, record_path)
            self._release_leaf(io, path)

    def _metadata(self, io, scope, version_id, *, write_integrity=False, record_id=None):
        identifier(version_id)
        routed_record = None
        try:
            if scope.record_ids is not None:
                routed_record = self._record_route(io, scope, version_id)
                scope.verify(routed_record)
                require(record_id is None or record_id == routed_record, "not_available")
            row = strict_json(io.read_bytes(self.project(scope) + "/versions/" + version_id + "/record.json", limit=META_LIMIT))
            # Keep visibility rejection at the same diagnostic boundary as
            # an absent/unverified reference, before detailed validation.
            require(isinstance(row, dict), "not_available" if not write_integrity and
                    (scope.audience != "owner" or scope.record_ids is not None) else "corrupt_record")
            if not write_integrity:
                audiences = row.get("audiences")
                if scope.audience == "owner" and scope.record_ids is None and record_id is None:
                    # Full-owner discovery must not report complete results
                    # after mistaking a damaged visibility envelope for denial.
                    require(isinstance(audiences, list) and bool(audiences), "corrupt_record")
                    for audience in audiences:
                        require(isinstance(audience, str), "corrupt_record")
                        identifier(audience)
                # A subset's record identity was verified by the route above.
                # Validate the envelope identity below, rather than hiding its
                # corruption as a second record-subset visibility rejection.
                require(isinstance(audiences, list) and scope.audience in audiences, "not_available")
        except (OSError, ValueError) as error:
            # Unverified explicit references share the ordinary unavailable
            # boundary, including its raise site. Discovery still fails closed.
            if isinstance(error, RecordsError) and (error.code == "authority_failed" or
                    (error.code == "routing_unavailable" and record_id is None)):
                raise
            if not write_integrity and (scope.audience != "owner" or scope.record_ids is not None):
                raise RecordsError("not_available") from None
            raise
        finally:
            self._release_leaf(io, self.project(scope) + "/versions/" + version_id)
        keys(row, "contract project_id record_id version_id operation_id request_sha256 title kind work_id source audiences original_created_at received_at parent related body")
        require(row["contract"] == CONTRACT and row["project_id"] == scope.project_id and row["version_id"] == version_id, "corrupt_record")
        identifier(row["record_id"])
        require(routed_record is None or row["record_id"] == routed_record, "corrupt_record")
        identifier(row["operation_id"])
        sha(row["request_sha256"])
        require(isinstance(row["kind"], str) and row["kind"] in KINDS and isinstance(row["title"], str), "corrupt_record")
        require(row["work_id"] is None or isinstance(row["work_id"], str), "corrupt_record")
        require(isinstance(row["audiences"], list) and bool(row["audiences"]), "corrupt_record")
        for audience in row["audiences"]:
            identifier(audience)
        keys(row["body"], "storage sha256 size reference")
        sha(row["body"]["sha256"])
        require(type(row["body"]["size"]) is int and 0 <= row["body"]["size"] <= BODY_LIMIT, "corrupt_record")
        require(isinstance(row["body"]["storage"], str) and row["body"]["storage"] in {"inline", "reference"}, "corrupt_record")
        require((row["body"]["reference"] is None) == (row["body"]["storage"] == "inline"), "corrupt_record")
        if row["body"]["reference"] is not None:
            self._validate_external(row["body"]["reference"])
            require(row["body"]["reference"]["sha256"] == row["body"]["sha256"], "corrupt_record")
        if row["parent"] is not None:
            ref_key(row["parent"])
        require(isinstance(row["related"], list) and len(row["related"]) <= 64, "corrupt_record")
        for ref in row["related"]:
            ref_key(ref)
        keys(row["source"], "authorship origin")
        require(isinstance(row["source"]["authorship"], str) and row["source"]["authorship"] in AUTHORSHIP and
                (row["source"]["origin"] is None or isinstance(row["source"]["origin"], str)), "corrupt_record")
        require(row["version_id"] == "v-" + digest(encoded([scope.project_id, row["operation_id"]])), "corrupt_record")
        expected_record = row["parent"]["record_id"] if row["parent"] else "r-" + digest(encoded([scope.project_id, row["operation_id"]]))
        require(row["record_id"] == expected_record, "corrupt_record")
        require(all(ref["project_id"] == scope.project_id for ref in row["related"] + ([row["parent"]] if row["parent"] else [])), "corrupt_record")
        request = {key: value for key, value in row.items() if key not in
                   {"contract", "project_id", "record_id", "version_id", "request_sha256", "received_at"}}
        require(digest(encoded(request)) == row["request_sha256"], "corrupt_record")
        timestamp(row["received_at"])
        timestamp(row["original_created_at"], nullable=True)
        return row

    @staticmethod
    def reference(row):
        return {"contract": CONTRACT, **{k: row[k] for k in ("project_id", "record_id", "version_id")}, "sha256": row["body"]["sha256"]}

    def _visible(self, row, scope):
        return isinstance(row.get("audiences"), list) and scope.audience in row["audiences"] and (
            scope.record_ids is None or isinstance(row.get("record_id"), str) and row["record_id"] in scope.record_ids)

    def _project_metadata(self, io, scope, row):
        # A readable record does not make every linked record readable.
        result = dict(row)
        # The canonical retry fingerprint also binds nonreturned relations.
        # Returning it would let a consumer distinguish a redacted relation
        # from an empty relation by hashing the otherwise complete projection.
        # Keep it internal for every audience so omission itself is not a signal.
        result.pop("request_sha256")
        result["related"] = []
        for ref in row["related"]:
            try:
                scope.verify(ref["record_id"])
                target = self._metadata(io, scope, ref["version_id"], record_id=ref["record_id"])
                require(self.reference(target) == ref, "stale_reference")
                result["related"].append(dict(ref))
            except RecordsError as error:
                if error.code != "not_available":
                    raise
        return result

    def _resolve(self, reference, scope):
        require(callable(self.resolver), "reference_unavailable")
        try:
            raw = self.resolver(dict(reference), scope)
        except RecordsError as error:
            if error.code == "authority_failed":
                raise RecordsError("authority_failed") from None
            raise RecordsError("reference_unavailable") from None
        except Exception:
            raise RecordsError("reference_unavailable") from None
        require(isinstance(raw, bytes) and len(raw) <= BODY_LIMIT, "reference_unavailable")
        return raw

    @staticmethod
    def _validate_external(reference):
        keys(reference, "producer version path sha256")
        identifier(reference["producer"])
        require(isinstance(reference["version"], str) and 0 < len(reference["version"]) <= 128, "invalid_schema")
        require(isinstance(reference["path"], str) and not Path(reference["path"]).is_absolute(), "invalid_schema")
        from .safeio import relative_name
        try:
            relative_name(Path("/"), reference["path"])
        except ValueError:
            raise RecordsError("invalid_schema") from None
        sha(reference["sha256"])

    def _read(self, io, scope, ref):
        ref_key(ref)
        require(ref["project_id"] == scope.project_id, "not_available")
        scope.verify(ref["record_id"])
        row = self._metadata(io, scope, ref["version_id"], record_id=ref["record_id"])
        require(self._visible(row, scope), "not_available")
        require(self.reference(row) == ref, "stale_reference")
        if row["body"]["storage"] == "inline":
            try:
                raw = io.read_inline_body(
                    self.project(scope) + "/versions/" + ref["version_id"] + "/body.bin",
                    expected_sha256=ref["sha256"], expected_size=row["body"]["size"],
                    verify=lambda: scope.verify(row["record_id"]))
            finally:
                self._release_leaf(io, self.project(scope) + "/versions/" + ref["version_id"])
        else:
            scope.verify(row["record_id"])
            raw = self._resolve(row["body"]["reference"], scope)
            require(digest(raw) == ref["sha256"], "stale_reference")
        require(len(raw) == row["body"]["size"], "corrupt_record")
        scope.verify(row["record_id"])
        return row, raw

    def read(self, scope, ref, *, include_body=True):
        with self.session(scope) as io:
            if not include_body:
                ref_key(ref)
                require(ref["project_id"] == scope.project_id, "not_available")
                scope.verify(ref["record_id"])
                row = self._metadata(io, scope, ref["version_id"], record_id=ref["record_id"])
                require(self._visible(row, scope), "not_available")
                require(self.reference(row) == ref, "stale_reference")
                scope.verify(ref["record_id"])
                return {"metadata": self._project_metadata(io, scope, row), "ref": dict(ref)}
            row, raw = self._read(io, scope, ref)
            return {"metadata": self._project_metadata(io, scope, row), "body": raw, "ref": dict(ref)}

    def operation(self, scope, operation_id, *, include_body=True):
        """Read one exact operation, without enumerating versions or bodies.

        Absence and out-of-scope operations share the unavailable boundary.
        Corrupt owner records and changed authority still fail closed.
        """
        identifier(operation_id)
        version_id = "v-" + digest(encoded([scope.project_id, operation_id]))
        try:
            with self.session(scope) as io:
                row = self._metadata(io, scope, version_id)
                require(row["operation_id"] == operation_id, "corrupt_record")
                result = {"metadata": self._project_metadata(io, scope, row),
                          "ref": self.reference(row)}
                if include_body:
                    row, raw = self._read(io, scope, self.reference(row))
                    result["body"] = raw
                return result
        except RecordsError as error:
            if error.code == "not_available":
                return None
            raise

    def metadata(self, scope):
        if isinstance(scope.record_ids, frozenset) and not scope.record_ids:
            # Validate live authority without opening the data root or even
            # enumerating a version namespace when no record is authorized.
            scope.verify()
            scope.verify()
            return []
        with self.session(scope) as io:
            result = []
            versions, generation = self._query_versions(io, scope)
            for version_id in versions:
                try:
                    row = self._metadata(io, scope, version_id)
                except RecordsError as error:
                    if error.code == "not_available":
                        continue
                    raise
                if self._visible(row, scope):
                    scope.verify(row["record_id"])
                    result.append(self._project_metadata(io, scope, row))
            self._verify_query_generation(io, scope, generation)
            return result

    def save(self, scope, *, operation_id, body, title="", kind="fragment", work_id=None,
             source=None, audiences=None, parent=None, related=(), original_created_at=None, reference=None):
        identifier(operation_id)
        require(isinstance(body, bytes) and len(body) <= BODY_LIMIT, "invalid_body")
        require(isinstance(title, str) and len(title) <= 4096 and isinstance(kind, str) and kind in KINDS, "invalid_request")
        if work_id is not None:
            identifier(work_id)
        require(original_created_at is None or isinstance(original_created_at, str) and len(original_created_at) <= 128, "invalid_request")
        timestamp(original_created_at, nullable=True)
        source = source if source is not None else {"authorship": "unknown", "origin": None}
        keys(source, "authorship origin")
        require(isinstance(source["authorship"], str) and source["authorship"] in AUTHORSHIP, "invalid_request")
        require(source["origin"] is None or isinstance(source["origin"], str) and len(source["origin"]) <= 4096, "invalid_request")
        source = dict(source)
        require(audiences is None or isinstance(audiences, (list, tuple)) and bool(audiences), "invalid_scope")
        audiences = [scope.audience] if audiences is None else list(audiences)
        for audience in audiences:
            identifier(audience)
        audiences = sorted(set(audiences))
        require(scope.audience in audiences, "invalid_scope")
        if parent is not None:
            ref_key(parent)
            require(parent["project_id"] == scope.project_id, "not_available")
            parent = dict(parent)
        related = list(related)
        require(len(related) <= 64, "invalid_request")
        for ref in related:
            ref_key(ref)
            require(ref["project_id"] == scope.project_id, "not_available")
        related = [dict(ref) for ref in related]
        if reference is not None:
            self._validate_external(reference)
            reference = dict(reference)
            require(reference["sha256"] == digest(body), "stale_reference")
            require(callable(self.resolver), "reference_unavailable")
        request = {"operation_id": operation_id, "title": title, "kind": kind, "work_id": work_id,
                   "source": source, "audiences": audiences, "parent": parent, "related": related,
                   "original_created_at": original_created_at,
                   "body": {"storage": "reference" if reference is not None else "inline", "sha256": digest(body), "size": len(body), "reference": reference}}
        request_hash = digest(encoded(request))
        version_id = "v-" + digest(encoded([scope.project_id, operation_id]))
        record_id = parent["record_id"] if parent else "r-" + digest(encoded([scope.project_id, operation_id]))
        scope.verify(record_id, write=True)
        # A subset alone cannot prove a complete CAS history if identity routes
        # were damaged. Never gain project-wide reads for a restricted writer.
        require(scope.record_ids is None, "restricted_write_unavailable")
        with self.session(scope, write=True, record_id=record_id) as io, self.lock(io, scope) as project:
            if reference is not None:
                require(self._resolve(reference, scope) == body, "stale_reference")
            io.mkdir(project + "/versions")
            versions = self._directories(io, project + "/versions")
            if version_id in versions:
                row = self._metadata(io, scope, version_id)
                require(row["request_sha256"] == request_hash and self._visible(row, scope), "operation_conflict")
                self._read(io, scope, self.reference(row))
                io._records_published = True
                self._durable(io, scope, "versions")
                return {"status": "retry", "ref": self.reference(row)}
            if parent:
                old, _ = self._read(io, scope, parent)
                require(old["work_id"] == work_id and old["audiences"] == audiences, "revision_scope_changed")
                children = []
                for v in versions:
                    # Internal integrity inspection exposes no foreign metadata.
                    # Never hide a corrupted child's existence from the CAS by
                    # trusting its unauthenticated audience label first.
                    children.append(self._metadata(io, scope, v, write_integrity=True))
                require(not any(r["parent"] and r["parent"]["version_id"] == parent["version_id"] for r in children), "parent_conflict")
            for ref in related:
                self._read(io, scope, ref)
            row = {"contract": CONTRACT, "project_id": scope.project_id, "record_id": record_id, "version_id": version_id,
                   "request_sha256": request_hash, "received_at": datetime.now(timezone.utc).isoformat(), **request}
            require(len(encoded(row)) <= META_LIMIT, "invalid_request")
            self._commit(io, scope, "versions", version_id, {"body.bin": body} if reference is None else {}, "record.json", row)
            return {"status": "created", "ref": self.reference(row)}

    def _commit(self, io, scope, collection, object_id, files, metadata_name, row):
        project = self.project(scope)
        io.mkdir(project + "/pending")
        io.mkdir(project + "/" + collection)
        stage = project + "/pending/p-" + uuid.uuid4().hex
        io.mkdir(stage, exclusive=True)
        self.fault("temporary")
        for name, raw in files.items():
            io.write_new(stage + "/" + name, raw)
        self.fault("body")
        io.write_new(stage + "/" + metadata_name, encoded(row))
        self.fault("metadata")
        if collection == "versions":
            self._stage_record_route(io, stage, scope.project_id, object_id, row["record_id"])
        self._sync(io, stage)
        scope.verify(write=True)
        io._verify_dirs()
        source = io.directory(tuple((project + "/pending").split("/")))
        dest = io.directory(tuple((project + "/" + collection).split("/")))
        require(object_id not in os.listdir(dest), "operation_conflict")
        os.rename(stage.rsplit("/", 1)[-1], object_id, src_dir_fd=source, dst_dir_fd=dest)
        io._records_published = True
        try:
            self._durable(io, scope, collection)
            self.fault("published")
        except (OSError, RuntimeError):
            raise RecordsError("outcome_unknown") from None

    def _durable(self, io, scope, collection):
        project = self.project(scope)
        for path in (project + "/" + collection, project + "/pending", project, "projects"):
            self._sync(io, path)
        os.fsync(io.directory(()))

    def _stage_record_route(self, io, stage, project_id, version_id, record_id):
        binding = "k-" + digest(encoded([project_id, version_id, record_id]))
        io.mkdir(stage + "/identity")
        io.mkdir(stage + "/identity/" + record_id)
        io.mkdir(stage + "/identity/" + record_id + "/" + binding)
        self._sync(io, stage + "/identity/" + record_id + "/" + binding)
        self._sync(io, stage + "/identity/" + record_id)
        self._sync(io, stage + "/identity")
        self._release_leaf(io, stage + "/identity/" + record_id + "/" + binding)
        self._release_leaf(io, stage + "/identity/" + record_id)
        self._release_leaf(io, stage + "/identity")

    def bind_record_routes(self, scope):
        """Explicit, idempotent full-owner upgrade of legacy identity routes.

        Preserve canonical record.json/body.bin bytes and all reference IDs.
        No restricted discovery, automatic fallback or producer call occurs.
        """
        scope.verify(write=True)
        require(scope.audience == "owner" and scope.record_ids is None, "restricted_write_unavailable")
        with self.session(scope, write=True) as io, self.lock(io, scope) as project:
            versions = self._directories(io, project + "/versions")
            for version_id in versions:
                row = self._metadata(io, scope, version_id, write_integrity=True)
                version_path = project + "/versions/" + version_id
                try:
                    route = self._record_route(io, scope, version_id, required=False)
                    if route is None:
                        io.mkdir(project + "/pending")
                        stage = project + "/pending/p-" + uuid.uuid4().hex
                        io.mkdir(stage)
                        self._stage_record_route(io, stage, scope.project_id, version_id, row["record_id"])
                        self._sync(io, stage)
                        scope.verify(write=True)
                        src = io.directory(tuple(stage.split("/")))
                        dest = io.directory(tuple(version_path.split("/")))
                        io._verify_dirs(tuple(version_path.split("/")))
                        require("identity" not in os.listdir(dest), "routing_unavailable")
                        os.rename("identity", "identity", src_dir_fd=src, dst_dir_fd=dest)
                        io._records_published = True
                        try:
                            self._release_leaf(io, stage)
                            self.fault("routing_published")
                        except Exception:
                            raise RecordsError("outcome_unknown") from None
                    else:
                        require(route == row["record_id"], "routing_unavailable")
                        io._records_published = True
                    self._sync(io, version_path)
                    self._durable(io, scope, "versions")
                finally:
                    self._release_leaf(io, version_path)
            return {"versions": len(versions)}

    def rebuild_index(self, scope):
        """Derived navigation cache only. Readers never trust it for access/data."""
        with self.session(scope, write=True) as io, self.lock(io, scope) as project:
            refs = []
            versions = [] if scope.record_ids == frozenset() else self._directories(io, project + "/versions")
            for v in versions:
                try:
                    row = self._metadata(io, scope, v)
                except RecordsError as error:
                    if error.code == "not_available":
                        continue
                    raise
                if self._visible(row, scope):
                    self._read(io, scope, self.reference(row))
                    refs.append(self.reference(row))
            self.fault("index")
            value = {"contract": CONTRACT, "audience": scope.audience, "refs": refs}
            # Cache is immutable by content; deleting it never deletes originals.
            io.mkdir(project + "/indexes")
            name = digest(encoded(value))
            path = project + "/indexes/" + name + ".json"
            try:
                previous = io.read_bytes(path, limit=16 * 1024 * 1024)
                require(previous == encoded(value), "corrupt_record")
            except FileNotFoundError:
                io.publish_record(path, encoded(value))
                self._sync(io, project + "/indexes")
            return {"index_sha256": name, "versions": len(refs)}
