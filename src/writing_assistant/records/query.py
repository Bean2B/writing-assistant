"""Scoped exact recall and literal Unicode keyword search; no model/index trust."""
import base64
from contextlib import contextmanager, nullcontext
import json
import os

from .core import RecordsError, digest, encoded, identifier, require
from .continuation import ContextBudgetError


def _display(store, row):
    return {"ref": store.reference(row), "title": row["title"], "kind": row["kind"],
            "work_id": row["work_id"], "received_at": row["received_at"],
            "source": row["source"], "parent": row["parent"], "related": row["related"]}


def list_records(store, scope, *, keyword=None, work_id=None, all_versions=False,
                 limit=20, cursor=None, case_sensitive=True, max_bytes=32768,
                 scan_limit=None):
    if scan_limit is not None:
        # Incremental search has all-version semantics. Global latest selection
        # still requires the capped complete metadata pass below.
        require(type(all_versions) is bool and all_versions, "invalid_request")
        return _scan(store, scope, keyword=keyword, work_id=work_id, limit=limit,
                     cursor=cursor, case_sensitive=case_sensitive, max_bytes=max_bytes,
                     scan_limit=scan_limit)
    require(type(limit) is int and 1 <= limit <= 200, "invalid_request")
    require(type(max_bytes) is int and 0 < max_bytes <= 16 * 1024 * 1024, "invalid_request")
    require(type(all_versions) is bool and type(case_sensitive) is bool, "invalid_request")
    require(keyword is None or isinstance(keyword, str) and 0 < len(keyword) <= 4096, "invalid_request")
    if work_id is not None:
        identifier(work_id)
    with _query_scope(store, scope) as binding:
        return _complete_records(store, scope, keyword=keyword, work_id=work_id,
                                 all_versions=all_versions, limit=limit, cursor=cursor,
                                 case_sensitive=case_sensitive, max_bytes=max_bytes, binding=binding)


def _complete_records(store, scope, *, keyword, work_id, all_versions, limit,
                      cursor, case_sensitive, max_bytes, binding):
    rows = store.metadata(scope)  # Current scope before any returned title/snippet.
    sources = rows
    if work_id is not None:
        rows = [r for r in rows if r["work_id"] == work_id]
    if not all_versions:
        parent_ids = {r["parent"]["version_id"] for r in rows if r["parent"]}
        rows = [r for r in rows if r["version_id"] not in parent_ids]
    rows.sort(key=lambda r: (r["received_at"], r["version_id"]), reverse=True)
    results = []
    needle = keyword if case_sensitive or keyword is None else keyword.casefold()
    with store.session(scope) if keyword is not None and rows else nullcontext() as io:
        for row in rows:
            item = _display(store, row)
            if keyword is not None:
                # Reuse root handles, not validated content or permissions.
                # Keep the checks/projection of each former public read call.
                scope.verify()
                current, body = store._read(io, scope, item["ref"])
                store._project_metadata(io, scope, current)
                scope.verify()
                io._verify_dirs(tuple(store.project(scope).split("/")))
                try:
                    text = body.decode("utf-8")
                except UnicodeError:
                    raise RecordsError("unsupported_encoding") from None
                title = row["title"]
                haystack = title + "\n" + text
                if not case_sensitive:
                    haystack = haystack.casefold()
                if needle not in haystack:
                    continue
                item["excerpt"] = text[:160]
                item["excerpt_complete"] = len(text) <= 160
                item["excerpt_range"] = [0, min(160, len(text))]
            results.append(item)
    snapshot = _snapshot(store, scope, "recent", {"binding": binding, "sources": sources,
                         "keyword": keyword, "work_id": work_id, "all_versions": all_versions,
                         "case_sensitive": case_sensitive, "items": results})
    offset = 0
    if cursor is not None:
        require(isinstance(cursor, str) and len(cursor) <= 512, "invalid_cursor")
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        except (ValueError, UnicodeError):
            raise RecordsError("invalid_cursor") from None
        require(isinstance(token, dict) and set(token) == {"snapshot", "offset"} and
                type(token["offset"]) is int and 0 <= token["offset"] <= len(results), "invalid_cursor")
        require(token["snapshot"] == snapshot, "stale_cursor")
        offset = token["offset"]
    def page(end):
        next_cursor = None if end == len(results) else base64.urlsafe_b64encode(
            encoded({"snapshot": snapshot, "offset": end})).decode("ascii")
        return {"items": [], "total": len(results), "next_cursor": next_cursor,
                "range": [offset, end], "originals_truncated": False}

    end, item_bytes = offset, 0
    result = page(end)
    required_bytes = len(encoded(result))
    for candidate_end in range(offset + 1, min(offset + limit, len(results)) + 1):
        item_bytes += len(encoded(results[candidate_end - 1])) - 1
        candidate = page(candidate_end)
        # Each item is measured once. The empty-array envelope already includes
        # cursor/range metadata and the same compact UTF-8 transport newline.
        size = len(encoded(candidate)) + item_bytes + candidate_end - offset - 1
        if size > max_bytes:
            if end == offset:
                required_bytes = size
            break
        end, result, required_bytes = candidate_end, candidate, size
    scope.verify()
    if required_bytes > max_bytes:
        # Refuse without advancing the caller's cursor or trimming metadata.
        raise ContextBudgetError(required_bytes, max_bytes)
    result["items"] = results[offset:end]
    return result


def history(store, scope, record_id, *, limit=None, cursor=None, max_bytes=32768):
    if limit is not None:
        _bounds(limit, max_bytes)
    identifier(record_id)
    scope.verify(record_id)
    with _query_scope(store, scope) as binding:
        return _complete_history(store, scope, record_id, limit=limit, cursor=cursor,
                                 max_bytes=max_bytes, binding=binding)


def _complete_history(store, scope, record_id, *, limit, cursor, max_bytes, binding):
    rows = [r for r in store.metadata(scope) if r["record_id"] == record_id]
    require(bool(rows), "not_available")
    by_id = {r["version_id"]: r for r in rows}
    for row in rows:
        if row["parent"]:
            parent = by_id.get(row["parent"]["version_id"])
            require(parent is not None and store.reference(parent) == row["parent"], "corrupt_record")
    children = {r["parent"]["version_id"]: r["version_id"] for r in rows if r["parent"]}
    require(len(children) == sum(bool(r["parent"]) for r in rows), "corrupt_record")
    roots = [r for r in rows if r["parent"] is None]
    require(len(roots) == 1, "corrupt_record")
    ordered, row = [], roots[0]
    while row is not None:
        require(len(ordered) < len(rows), "corrupt_record")
        ordered.append(_display(store, row))
        child = children.get(row["version_id"])
        row = by_id.get(child) if child else None
    require(len(ordered) == len(rows), "corrupt_record")
    snapshot = _snapshot(store, scope, "history", {"binding": binding, "versions": ordered})
    offset, _ = _position(cursor, snapshot, len(ordered))
    if limit is None:
        require(cursor is None, "invalid_request")
        selected = ordered
    else:
        def page(end):
            return {"record_id": record_id, "versions": ordered[offset:end],
                    "latest_stored": ordered[-1]["ref"], "continuation_selection": None,
                    "adoption": "not_determined_by_records", "total": len(ordered),
                    "range": [offset, end], "next_cursor": _cursor(snapshot, end, end)
                    if end < len(ordered) else None, "originals_truncated": False}
        try:
            result = _fit(page, offset, min(offset + limit, len(ordered)), max_bytes)
        except ContextBudgetError:
            if offset < len(ordered):
                store.read(scope, ordered[offset]["ref"])
            scope.verify(record_id)
            raise
        selected = result["versions"]
    for item in selected:
        store.read(scope, item["ref"])
    scope.verify(record_id)
    if limit is not None:
        return result
    return {"record_id": record_id, "versions": ordered,
            "latest_stored": ordered[-1]["ref"], "continuation_selection": None,
            "adoption": "not_determined_by_records"}


@contextmanager
def _query_scope(store, scope):
    """Keep physical root and namespace generation bound through page delivery."""
    scope.verify()
    if scope.record_ids == frozenset():
        yield None
        scope.verify()
        return
    with store.session(scope) as io:
        names, generation = store._query_versions(io, scope)
        root = os.fstat(io._dirs[()])
        binding = {"root": [root.st_dev, root.st_ino], "names": names, "generation": generation}
        try:
            yield binding
        except ContextBudgetError:
            scope.verify()
            store._verify_query_generation(io, scope, generation)
            raise
        scope.verify()
        store._verify_query_generation(io, scope, generation)


def _bounds(limit, max_bytes, scan_limit=None):
    require(type(limit) is int and 1 <= limit <= 200, "invalid_request")
    require(type(max_bytes) is int and 0 < max_bytes <= 16 * 1024 * 1024, "invalid_request")
    require(scan_limit is None or type(scan_limit) is int and 1 <= scan_limit <= 2000,
            "invalid_request")


def _snapshot(store, scope, operation, sources):
    return digest(encoded({"root": str(store.root.absolute()), "project": scope.project_id,
                           "audience": scope.audience, "records": None if scope.record_ids is None
                           else sorted(scope.record_ids), "operation": operation, "sources": sources}))


def _cursor(snapshot, offset, returned):
    return base64.urlsafe_b64encode(encoded({"snapshot": snapshot, "offset": offset,
                                            "returned": returned})).decode("ascii")


def _position(cursor, snapshot, count):
    if cursor is None:
        return 0, 0
    require(isinstance(cursor, str) and 0 < len(cursor) <= 512, "invalid_cursor")
    try:
        token = json.loads(base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True))
    except (ValueError, UnicodeError, RecursionError):
        raise RecordsError("invalid_cursor") from None
    require(type(token) is dict and set(token) == {"snapshot", "offset", "returned"}
            and type(token["offset"]) is int and 0 <= token["offset"] <= count
            and type(token["returned"]) is int and 0 <= token["returned"] <= token["offset"],
            "invalid_cursor")
    require(token["snapshot"] == snapshot, "stale_cursor")
    return token["offset"], token["returned"]


def _fit(page, offset, stop, max_bytes):
    result = page(offset)
    required = len(encoded(result))
    for end in range(offset + 1, stop + 1):
        candidate = page(end)
        size = len(encoded(candidate))
        if size > max_bytes:
            if end == offset + 1:
                required = size
            break
        result, required = candidate, size
    if required > max_bytes:
        raise ContextBudgetError(required, max_bytes)
    return result


def list_metadata(store, scope, *, limit=20, cursor=None, max_bytes=32768, scan_limit=100):
    """Read a bounded slice of canonical metadata in stable version-ID order."""
    return _scan(store, scope, metadata=True, limit=limit, cursor=cursor,
                 max_bytes=max_bytes, scan_limit=scan_limit)


def _scan(store, scope, *, metadata=False, keyword=None, work_id=None, limit=20,
          cursor=None, case_sensitive=True, max_bytes=32768, scan_limit=100):
    _bounds(limit, max_bytes, scan_limit)
    require(type(case_sensitive) is bool, "invalid_request")
    require(keyword is None or isinstance(keyword, str) and 0 < len(keyword) <= 4096,
            "invalid_request")
    if work_id is not None:
        identifier(work_id)
    scope.verify()
    empty = scope.record_ids == frozenset()
    with nullcontext() if empty else store.session(scope) as io:
        names, generation = ([], None) if empty else store._query_versions(io, scope)
        binding = {"names": names, "generation": generation, "keyword": keyword,
                   "work_id": work_id, "case_sensitive": case_sensitive}
        if not empty:
            root = os.fstat(io._dirs[()])
            binding["root"] = [root.st_dev, root.st_ino]
        snapshot = _snapshot(store, scope, "list" if metadata else "search", binding)
        offset, returned = _position(cursor, snapshot, len(names))
        end, scanned, items = offset, 0, []
        key = "versions" if metadata else "items"

        def page():
            return {key: items, "total": None, "range": [returned, returned + len(items)],
                    "next_cursor": _cursor(snapshot, end, returned + len(items)) if end < len(names) else None,
                    "originals_truncated": False, "scan": {"scanned": scanned, "complete": end == len(names)}}

        needle = keyword if case_sensitive or keyword is None else keyword.casefold()
        required = None
        while end < len(names) and scanned < scan_limit and len(items) < limit:
            scope.verify()
            version_id = names[end]
            scanned += 1
            try:
                row = store._metadata(io, scope, version_id)
            except RecordsError as error:
                if error.code == "not_available":
                    end += 1
                    continue
                raise
            if not store._visible(row, scope) or work_id is not None and row["work_id"] != work_id:
                end += 1
                continue
            row = store._project_metadata(io, scope, row)
            item = row if metadata else _display(store, row)
            if keyword is not None:
                current, body = store._read(io, scope, item["ref"])
                store._project_metadata(io, scope, current)
                try:
                    text = body.decode("utf-8")
                except UnicodeError:
                    raise RecordsError("unsupported_encoding") from None
                haystack = row["title"] + "\n" + text
                if not case_sensitive:
                    haystack = haystack.casefold()
                if needle not in haystack:
                    end += 1
                    continue
                item.update(excerpt=text[:160], excerpt_complete=len(text) <= 160,
                            excerpt_range=[0, min(160, len(text))])
            items.append(item)
            end += 1
            size = len(encoded(page()))
            if size > max_bytes:
                items.pop()
                end -= 1
                if not items:
                    required = size
                break
        result = page()
        # Do not disclose sizes or a continuation after a late authority change.
        scope.verify()
        if not empty:
            store._verify_query_generation(io, scope, generation)
        size = len(encoded(result))
        scope.verify()
        if required is not None or size > max_bytes:
            raise ContextBudgetError(required if required is not None else size, max_bytes)
        return result


def show(store, scope, ref):
    return store.read(scope, ref)
