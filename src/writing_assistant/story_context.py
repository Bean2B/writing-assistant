"""Bounded exact prose selection over an explicitly supplied story index.

Receipts preserve the selected state, selection reasons and exclusions. They
contain no prose summary. Selected original bytes travel as exact record
materials (and explicit byte ranges) to the existing durable task API.
"""

from contextlib import contextmanager
import fcntl
import os
import stat

from . import story_state
from .core.errors import AssistantError, require
from .core.jsonio import canonical, decode, digest, fields
from .records.application import owner_store

CONTRACT = "writing-assistant-story-context/1"
REQUEST_CONTRACT = "writing-assistant-story-context-request/1"
MAX_BYTES = 262144
MAX_ITEMS = 24


def _operation(scope, context_id):
    return "story-context-" + digest(canonical([scope.project_id, context_id]))


@contextmanager
def _lock(store, scope, context_id):
    caught = None
    with store.session(scope, write=True) as io:
        parts = tuple((store.project(scope) + "/story-context-locks").split("/"))
        parent = io.directory(parts, create=True)
        io._verify_dirs(parts)
        name = context_id + ".lock"
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        held = False
        try:
            row = os.fstat(fd)
            require(stat.S_ISREG(row.st_mode) and row.st_nlink == 1, "invalid_story_context_lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AssistantError("busy") from None
            held = True
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require((row.st_dev, row.st_ino) == (current.st_dev, current.st_ino), "invalid_story_context_lock")
            scope.verify(write=True)
            yield
            scope.verify(write=True)
        except AssistantError as error:
            caught = error
        finally:
            if held:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    if caught is not None:
        raise caught


def _normalize(value, project_id):
    value = decode(canonical(value))
    fields(value, ("schema_version", "context_id", "project_id"),
           ("state", "earlier_prose", "recent_chapters", "tags", "max_bytes", "max_items"))
    require(value["schema_version"] == REQUEST_CONTRACT, "unsupported_story_context_version")
    story_state._identifier(value["context_id"])
    require(value["project_id"] == project_id, "project_mismatch")
    value = {"state": None, "earlier_prose": [], "recent_chapters": [], "tags": [],
             "max_bytes": MAX_BYTES, "max_items": MAX_ITEMS, **value}
    require(type(value["max_bytes"]) is int and 1 <= value["max_bytes"] <= MAX_BYTES
            and type(value["max_items"]) is int and 1 <= value["max_items"] <= MAX_ITEMS,
            "invalid_story_context_bounds")
    story_state._tags(value["tags"])
    if value["state"] is not None:
        state = value["state"]
        fields(state, ("ref",), ("entry_ids", "tags"))
        story_state._ref(state["ref"], project_id)
        if "entry_ids" in state:
            require(type(state["entry_ids"]) is list and len(state["entry_ids"]) <= story_state.MAX_ENTRIES,
                    "invalid_story_selection")
            for entry_id in state["entry_ids"]:
                story_state._identifier(entry_id)
            require(len(set(state["entry_ids"])) == len(state["entry_ids"]), "duplicate_story_entry")
        if "tags" in state:
            story_state._tags(state["tags"])
    for category in ("earlier_prose", "recent_chapters"):
        items = value[category]
        require(type(items) is list and len(items) <= 64, "story_context_index_limit")
        for item in items:
            if category == "earlier_prose":
                fields(item, ("ref", "reason"), ("tags", "span"))
                story_state._text(item["reason"], 1024)
                story_state._tags(item.get("tags", []))
                if "span" in item:
                    fields(item["span"], ("start", "end", "sha256"))
                    story_state._evidence([{**item["span"], "ref": item["ref"]}], project_id)
            else:
                fields(item, ("ref", "chapter"))
                require(type(item["chapter"]) is int and 1 <= item["chapter"] <= 20000,
                        "invalid_story_context_chapter")
            story_state._ref(item["ref"], project_id)
    chapters = [item["chapter"] for item in value["recent_chapters"]]
    require(len(set(chapters)) == len(chapters), "duplicate_story_context_chapter")
    require(len(value["earlier_prose"]) + len(value["recent_chapters"]) <= 96, "story_context_index_limit")
    return value


def _selected_state(store, scope, request):
    state = request["state"]
    if state is None:
        return None
    return story_state.select_in_store(store, scope, state["ref"], entry_ids=state.get("entry_ids"),
                                       tags=state.get("tags", []), require_current=True)


def _candidates(store, scope, request):
    result, excluded, seen = [], [], set()
    # Newest recent chapters get first claim on the available bytes. The final
    # manifest uses this explicit order and never invents an implicit history.
    sources = [("recent-chapter", item) for item in sorted(request["recent_chapters"],
                                                          key=lambda item: item["chapter"], reverse=True)]
    sources += [("earlier-prose", item) for item in request["earlier_prose"]]
    for category, item in sources:
        reference = item["ref"]
        span = item.get("span")
        identity = canonical([reference, span])
        if identity in seen:
            excluded.append({"category": category, "ref": reference, "reason": "duplicate", "bytes": 0})
            continue
        seen.add(identity)
        # Unmatched explicitly indexed references are excluded before content
        # or metadata reads; their existence is not inferred from the library.
        if (category == "earlier-prose" and request["tags"] and item.get("tags")
                and not set(request["tags"]) & set(item["tags"])):
            excluded.append({"category": category, "ref": reference, "reason": "unmatched-tags", "bytes": None})
            continue
        metadata = store.read(scope, reference, include_body=False)["metadata"]
        require(metadata["kind"] in {"prose", "draft", "fragment"}, "invalid_story_prose_kind")
        size = metadata["body"]["size"]
        if span is not None:
            require(span["end"] <= size, "stale_story_evidence")
        row = {"category": category, "ref": reference, "start": 0 if span is None else span["start"],
               "end": size if span is None else span["end"],
               "sha256": reference["sha256"] if span is None else span["sha256"],
               "reason": "recent-chapter" if category == "recent-chapter" else item["reason"]}
        if category == "recent-chapter":
            row["chapter"] = item["chapter"]
        elif request["tags"] and item.get("tags"):
            row["matched_tags"] = sorted(set(request["tags"]) & set(item["tags"]))
        result.append(row)
    return result, excluded


def _packet(request, state, selected, excluded):
    return {"contract": CONTRACT, "request": request, "state": state, "selected": selected,
            "excluded": excluded, "selection_order": "state-then-recent-newest-then-explicit-earlier",
            "budget": {"max_bytes": request["max_bytes"], "max_items": request["max_items"],
                       "unit": "utf-8-bytes-including-receipt"},
            "adopted": False, "world_facts_written": False}


def _choose(request, state, candidates, excluded):
    selected = list(candidates)
    # Reserve the complete receipt and exact source bytes, including every
    # exclusion. Drop the lowest-priority item until that actual packet fits.
    while True:
        packet = _packet(request, state, selected, excluded)
        raw = canonical(packet)
        total = len(raw) + sum(item["end"] - item["start"] for item in selected)
        count = len(selected) + 1  # The state/selection receipt is a material.
        if total <= request["max_bytes"] and count <= request["max_items"]:
            return packet, raw, total
        require(bool(selected), "story_context_budget_exceeded")
        item = selected.pop()
        excluded.append({"category": item["category"], "ref": item["ref"],
                         "reason": "item-limit" if count > request["max_items"] else "budget",
                         "bytes": item["end"] - item["start"]})


def _verify_selected(store, scope, packet):
    for item in packet["selected"]:
        raw = store.read(scope, item["ref"])["body"]
        require(item["end"] <= len(raw), "stale_story_evidence")
        selected = raw[item["start"]:item["end"]]
        require(digest(selected) == item["sha256"], "stale_story_evidence")
        try:
            selected.decode("utf-8")
        except UnicodeError:
            raise AssistantError("invalid_story_context_encoding") from None


def _validate_packet(packet, project_id):
    fields(packet, ("contract", "request", "state", "selected", "excluded", "selection_order",
                    "budget", "adopted", "world_facts_written"))
    require(packet["contract"] == CONTRACT, "invalid_story_context_receipt")
    request = _normalize(packet["request"], project_id)
    require(request == packet["request"] and packet["adopted"] is False
            and packet["world_facts_written"] is False, "invalid_story_context_receipt")
    require(type(packet["selected"]) is list and len(packet["selected"]) < request["max_items"]
            and type(packet["excluded"]) is list and len(packet["excluded"]) <= 96,
            "invalid_story_context_receipt")
    for item in packet["selected"]:
        fields(item, ("category", "ref", "start", "end", "sha256", "reason"), ("chapter", "matched_tags"))
        require(item["category"] in {"recent-chapter", "earlier-prose"}, "invalid_story_context_receipt")
        story_state._ref(item["ref"], project_id)
        require(type(item["start"]) is int and type(item["end"]) is int
                and 0 <= item["start"] <= item["end"] <= 16777216, "invalid_story_context_receipt")
        require(type(item["sha256"]) is str and story_state.HASH.fullmatch(item["sha256"]),
                "invalid_story_context_receipt")
        story_state._text(item["reason"], 1024)
        if "matched_tags" in item:
            story_state._tags(item["matched_tags"])
        if item["category"] == "recent-chapter":
            require(type(item.get("chapter")) is int and any(
                source == {"ref": item["ref"], "chapter": item["chapter"]}
                for source in request["recent_chapters"]), "invalid_story_context_receipt")
        else:
            require(any(source["ref"] == item["ref"] and source["reason"] == item["reason"]
                        for source in request["earlier_prose"]), "invalid_story_context_receipt")
    for item in packet["excluded"]:
        fields(item, ("category", "ref", "reason", "bytes"))
        story_state._ref(item["ref"], project_id)
        require(item["category"] in {"recent-chapter", "earlier-prose"}
                and item["reason"] in {"duplicate", "unmatched-tags", "item-limit", "budget"}
                and (item["bytes"] is None or type(item["bytes"]) is int and 0 <= item["bytes"] <= 16777216),
                "invalid_story_context_receipt")
    require(_packet(request, packet["state"], packet["selected"], packet["excluded"]) == packet,
            "invalid_story_context_receipt")
    total = len(canonical(packet)) + sum(item["end"] - item["start"] for item in packet["selected"])
    require(total <= request["max_bytes"], "invalid_story_context_receipt")
    return request


def _view(packet, reference, raw):
    label = "story-context:" + packet["request"]["context_id"]
    materials = [{"uri": label, "sha256": reference["sha256"], "purpose": "current-writing",
                  "role": "request-material", "source_kind": "record-version"}]
    bindings = [{"uri": label, "ref": reference}]
    ranges = []
    for index, item in enumerate(packet["selected"]):
        uri = label + ":prose-" + str(index)
        materials.append({"uri": uri, "sha256": item["sha256"], "purpose": "current-writing",
                          "role": "prior-prose", "source_kind": "record-version"})
        bindings.append({"uri": uri, "ref": item["ref"]})
        ranges.append({"uri": uri, "start": item["start"], "end": item["end"]})
    return {"contract": CONTRACT, "reference": reference, "packet": packet, "materials": materials,
            "bindings": bindings, "ranges": ranges,
            "material_bytes": len(raw) + sum(item["end"] - item["start"] for item in packet["selected"]),
            "model_calls": 0}


def build_in_store(store, scope, request):
    """Save one idempotent exact selection receipt; dispatch no model."""
    request = _normalize(request, scope.project_id)
    with _lock(store, scope, request["context_id"]):
        existing = store.operation(scope, _operation(scope, request["context_id"]))
        state = _selected_state(store, scope, request)
        if existing is not None:
            packet = decode(existing["body"])
            _validate_packet(packet, scope.project_id)
            require(packet["contract"] == CONTRACT and packet["request"] == request
                    and packet["state"] == state and canonical(packet) == existing["body"],
                    "story_context_operation_conflict")
            _verify_selected(store, scope, packet)
            result = _view(packet, existing["ref"], existing["body"])
            require(result["material_bytes"] <= request["max_bytes"]
                    and len(result["materials"]) <= request["max_items"], "invalid_story_context_receipt")
            return result
        candidates, excluded = _candidates(store, scope, request)
        packet, raw, _ = _choose(request, state, candidates, excluded)
        _verify_selected(store, scope, packet)
        # Recheck live state after all material I/O and before publication.
        require(_selected_state(store, scope, request) == state, "stale_story_state")
        related = [item["ref"] for item in packet["selected"]]
        if state is not None:
            related.append(state["reference"])
        unique = {canonical(item): item for item in related}
        reference = store.save(scope, operation_id=_operation(scope, request["context_id"]), body=raw,
                               title="Story context selection", kind="decision", related=list(unique.values()),
                               source={"authorship": "unknown", "origin": "Explicit bounded selection; originals retained"})["ref"]
        require(_selected_state(store, scope, request) == state, "stale_story_state")
        return _view(packet, reference, raw)


def build(project, request, *, artifact_resolver=None):
    store, scope = owner_store(project, write=True, resolver=artifact_resolver)
    return build_in_store(store, scope, request)


def inspect(project, reference, *, artifact_resolver=None):
    """Read a saved receipt and authenticate every selected original again."""
    store, scope = owner_store(project, resolver=artifact_resolver)
    story_state._ref(reference, scope.project_id)
    saved = store.read(scope, reference)
    packet = decode(saved["body"])
    request = _validate_packet(packet, scope.project_id)
    require(saved["metadata"]["operation_id"] == _operation(scope, request["context_id"]),
            "invalid_story_context_receipt")
    require(packet["request"] == request and packet["state"] == _selected_state(store, scope, request)
            and canonical(packet) == saved["body"], "stale_story_state")
    _verify_selected(store, scope, packet)
    return _view(packet, reference, saved["body"])
