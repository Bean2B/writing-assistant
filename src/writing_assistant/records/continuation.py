"""Version-bound bookmarks and explicit bounded context, without generation."""
from datetime import datetime, timezone

from .core import RecordsError, digest, encoded, identifier, keys, ref_key, require, strict_json, timestamp

CONTRACT = "creative-continuation/1"


class ContextBudgetError(RecordsError):
    """An authorized continuation result's size, without source details."""

    def __init__(self, required_bytes, allowed_bytes):
        require(type(required_bytes) is int and type(allowed_bytes) is int
                and required_bytes > allowed_bytes > 0, "invalid_request")
        self.required_bytes = required_bytes
        self.allowed_bytes = allowed_bytes
        super().__init__("context_budget_exceeded")


def _text(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        raise RecordsError("unsupported_encoding") from None


def _range(value, length):
    require(isinstance(value, list) and len(value) == 2 and all(type(v) is int for v in value), "invalid_range")
    require(0 <= value[0] <= value[1] <= length, "invalid_range")
    return value


def _bookmark_ref(row):
    return {"contract": CONTRACT, "project_id": row["project_id"], "bookmark_id": row["bookmark_id"], "sha256": digest(encoded(row))}


def _load(store, io, scope, ref):
    keys(ref, "contract project_id bookmark_id sha256")
    require(ref["contract"] == CONTRACT, "unsupported_version")
    require(ref["project_id"] == scope.project_id, "not_available")
    identifier(ref["bookmark_id"])
    try:
        row = strict_json(io.read_bytes(store.project(scope) + "/bookmarks/" + ref["bookmark_id"] + "/bookmark.json", limit=1024 * 1024))
        require(isinstance(row, dict) and row.get("audience") == scope.audience, "not_available")
        keys(row, "contract project_id bookmark_id operation_id request_sha256 received_at audience selected stop decisions questions materials baseline")
    except (OSError, ValueError):
        if scope.audience != "owner" or scope.record_ids is not None:
            raise RecordsError("not_available") from None
        raise
    require(row["contract"] == CONTRACT and row["project_id"] == scope.project_id, "not_available")
    # Establish access to every referenced source before any bookmark integrity
    # diagnostic can distinguish an inaccessible bookmark from a missing one.
    try:
        require(isinstance(row["decisions"], list) and isinstance(row["materials"], list) and isinstance(row["questions"], list), "corrupt_record")
        require(len(row["decisions"]) + len(row["materials"]) + len(row["questions"]) <= 128, "corrupt_record")
        refs = [row["selected"]] + row["decisions"]
        for item in row["materials"]:
            keys(item, "ref range")
            refs.append(item["ref"])
        for item in row["questions"]:
            keys(item, "text source")
            if item["source"] is not None:
                refs.append(item["source"])
        length_needed = {row["selected"]["version_id"]} if isinstance(row["selected"], dict) and isinstance(row["selected"].get("version_id"), str) else set()
        length_needed.update(item["ref"]["version_id"] for item in row["materials"] if item["range"] is not None and isinstance(item["ref"], dict) and isinstance(item["ref"].get("version_id"), str))
        lengths = {}
        for source in refs:
            require(isinstance(source, dict) and isinstance(source.get("record_id"), str), "corrupt_record")
            scope.verify(source["record_id"])
            ref_key(source)
            _, raw = store._read(io, scope, source)
            if source["version_id"] in length_needed:
                lengths[source["version_id"]] = len(_text(raw))
    except RecordsError as error:
        if error.code in {"authority_failed", "routing_unavailable"}:
            raise
        if scope.audience != "owner" or scope.record_ids is not None:
            raise RecordsError("not_available") from None
        raise
    except (OSError, ValueError, KeyError, TypeError):
        if scope.audience != "owner" or scope.record_ids is not None:
            raise RecordsError("not_available") from None
        raise
    require(_bookmark_ref(row) == ref, "stale_reference")
    identifier(row["operation_id"])
    timestamp(row["received_at"])
    require(row["bookmark_id"] == "b-" + digest(encoded([scope.project_id, row["operation_id"]])), "corrupt_record")
    request = {k: v for k, v in row.items() if k not in {"contract", "project_id", "bookmark_id", "received_at", "request_sha256"}}
    require(digest(encoded(request)) == row["request_sha256"], "corrupt_record")
    require(row["stop"] is None or type(row["stop"]) is int and 0 <= row["stop"] <= lengths[row["selected"]["version_id"]], "invalid_range")
    for item in row["materials"]:
        if item["range"] is not None:
            _range(item["range"], lengths[item["ref"]["version_id"]])
    for item in row["questions"]:
        require(isinstance(item["text"], str), "corrupt_record")
    return row


def save_bookmark(store, scope, *, operation_id, selected, stop=None, decisions=(), questions=(), materials=(), baseline=None):
    identifier(operation_id)
    ref_key(selected)
    require(selected["project_id"] == scope.project_id, "not_available")
    require(baseline is None or isinstance(baseline, str) and len(baseline) <= 256, "invalid_request")
    decisions, questions, materials = list(decisions), list(questions), list(materials)
    require(len(decisions) + len(questions) + len(materials) <= 128, "invalid_request")
    with store.session(scope, write=True, record_id=selected["record_id"]) as io, store.lock(io, scope) as project:
        _, raw = store._read(io, scope, selected)
        length = len(_text(raw))
        require(stop is None or type(stop) is int and 0 <= stop <= length, "invalid_range")
        for ref in decisions:
            store._read(io, scope, ref)
        for question in questions:
            keys(question, "text source")
            require(isinstance(question["text"], str) and len(question["text"]) <= 4096, "invalid_request")
            if question["source"] is not None:
                store._read(io, scope, question["source"])
        for material in materials:
            keys(material, "ref range")
            _, content = store._read(io, scope, material["ref"])
            if material["range"] is not None:
                _range(material["range"], len(_text(content)))
        request = {"operation_id": operation_id, "audience": scope.audience, "selected": selected, "stop": stop,
                   "decisions": decisions, "questions": questions, "materials": materials, "baseline": baseline}
        row = {"contract": CONTRACT, "project_id": scope.project_id,
               "bookmark_id": "b-" + digest(encoded([scope.project_id, operation_id])),
               "request_sha256": digest(encoded(request)), "received_at": datetime.now(timezone.utc).isoformat(), **request}
        require(len(encoded(row)) <= 1024 * 1024, "invalid_request")
        io.mkdir(project + "/bookmarks")
        existing = store._directories(io, project + "/bookmarks")
        if row["bookmark_id"] in existing:
            old = strict_json(io.read_bytes(project + "/bookmarks/" + row["bookmark_id"] + "/bookmark.json", limit=1024 * 1024))
            keys(old, "contract project_id bookmark_id operation_id request_sha256 received_at audience selected stop decisions questions materials baseline")
            require(old.get("request_sha256") == row["request_sha256"], "operation_conflict")
            _load(store, io, scope, _bookmark_ref(old))
            io._records_published = True
            store._durable(io, scope, "bookmarks")
            return {"status": "retry", "bookmark": _bookmark_ref(old)}
        store._commit(io, scope, "bookmarks", row["bookmark_id"], {}, "bookmark.json", row)
        return {"status": "created", "bookmark": _bookmark_ref(row)}


def read_bookmark(store, scope, ref):
    with store.session(scope) as io:
        return _load(store, io, scope, ref)


def list_bookmarks(store, scope, *, limit=20, max_bytes=32768):
    """Discover recent exact selections for a full owner, without prose output."""
    require(type(limit) is int and 1 <= limit <= 200, "invalid_request")
    require(type(max_bytes) is int and 0 < max_bytes <= 16 * 1024 * 1024, "invalid_request")
    scope.verify()
    require(scope.audience == "owner" and scope.record_ids is None, "not_available")
    with store.session(scope) as io:
        path = store.project(scope) + "/bookmarks"
        items, total = [], 0
        # Scan every saved envelope within the existing session's I/O/deadline
        # budget. Never label a partial scan's newest candidate as latest.
        for bookmark_id in store._directories(io, path):
            leaf = path + "/" + bookmark_id
            try:
                row = strict_json(io.read_bytes(leaf + "/bookmark.json", limit=1024 * 1024))
                keys(row, "contract project_id bookmark_id operation_id request_sha256 received_at audience selected stop decisions questions materials baseline")
                require(row["contract"] == CONTRACT and row["project_id"] == scope.project_id
                        and row["bookmark_id"] == bookmark_id, "corrupt_record")
                identifier(row["audience"])
                if row["audience"] != scope.audience:
                    continue
                ref = _bookmark_ref(row)
                row = _load(store, io, scope, ref)
                item = {"bookmark": ref, "selected": row["selected"], "received_at": row["received_at"],
                        "operation_id": row["operation_id"], "stop": row["stop"], "baseline": row["baseline"]}
                items.append(item)
                items.sort(key=lambda value: (datetime.fromisoformat(value["received_at"]),
                                              value["bookmark"]["bookmark_id"]), reverse=True)
                del items[limit:]
                total += 1
            finally:
                try:
                    io._verify_dirs(tuple(leaf.split("/")))
                finally:
                    store._release_leaf(io, leaf)
        result = {"contract": CONTRACT, "project_id": scope.project_id, "audience": scope.audience,
                  "items": items, "total": total, "more_available": total > len(items), "model_calls": 0}
        required_bytes = len(encoded(result))
    # Final authority/namespace checks precede both metadata and size disclosure.
    if required_bytes > max_bytes:
        raise ContextBudgetError(required_bytes, max_bytes)
    return result


def prepare_latest_context(store, scope, *, max_bytes=256 * 1024, baseline=None):
    """Resolve the latest saved bookmark once, retaining its exact selection."""
    require(type(max_bytes) is int and 0 < max_bytes <= 16 * 1024 * 1024, "invalid_request")
    found = list_bookmarks(store, scope, limit=1)
    require(bool(found["items"]), "not_available")
    return prepare_context(store, scope, found["items"][0]["bookmark"], max_bytes=max_bytes, baseline=baseline)


def prepare_context(store, scope, bookmark, *, max_bytes=256 * 1024, baseline=None):
    require(type(max_bytes) is int and 0 < max_bytes <= 16 * 1024 * 1024, "invalid_request")
    with store.session(scope) as io:
        row = _load(store, io, scope, bookmark)
        require(row["baseline"] == baseline, "stale_baseline")
        inputs = [{"ref": row["selected"], "range": None, "purpose": "selected_draft"}]
        inputs += [{"ref": ref, "range": None, "purpose": "decision"} for ref in row["decisions"]]
        inputs += [{**item, "purpose": "explicit_material"} for item in row["materials"]]
        inputs += [{"ref": q["source"], "range": None, "purpose": "question_source", "question_index": index}
                   for index, q in enumerate(row["questions"]) if q["source"] is not None]
        pieces = []
        positions, texts = {}, {}
        text_bytes = 0
        for item in inputs:
            _, raw = store._read(io, scope, item["ref"])
            text = _text(raw)
            chosen = [0, len(text)] if item["range"] is None else _range(item["range"], len(text))
            identity = (encoded(item["ref"]), tuple(chosen))
            use = {"purpose": item["purpose"]}
            if "question_index" in item:
                use["question_index"] = item["question_index"]
            if identity in positions:
                pieces[positions[identity]]["uses"].append(use)
                continue
            selected_text = text[chosen[0]:chosen[1]]
            piece = {"ref": item["ref"], "range": chosen, "purpose": item["purpose"],
                     "uses": [use], "text": "", "complete": chosen == [0, len(text)]}
            # Measure each unique JSON string once. Empty placeholders let the
            # final envelope include all roles without serializing an oversized
            # aggregate body. Retain text only while it can fit the caller's bound.
            text_bytes += len(encoded(selected_text)) - len(encoded(""))
            if text_bytes <= max_bytes:
                texts[len(pieces)] = selected_text
            else:
                texts.clear()
            positions[identity] = len(pieces)
            pieces.append(piece)
        result = {"contract": CONTRACT, "project_id": scope.project_id, "audience": scope.audience,
                  "bookmark": bookmark, "selected": row["selected"], "stop": row["stop"],
                  "offset_unit": "unicode_code_points_utf8_including_bom", "questions": row["questions"],
                  "baseline": baseline, "pieces": pieces,
                  "omissions": [{"ref": item["ref"], "included_range": item["range"]} for item in pieces if not item["complete"]],
                  "adoption": "not_determined_by_records", "model_calls": 0}
        required_bytes = len(encoded(result)) + text_bytes
        scope.verify(row["selected"]["record_id"])
        if required_bytes <= max_bytes:
            for index, piece in enumerate(pieces):
                piece["text"] = texts[index]
    # Leave the session successfully first, so its final authority and namespace
    # checks also precede any size disclosure, including a refusal.
    if required_bytes > max_bytes:
        raise ContextBudgetError(required_bytes, max_bytes)
    return result
