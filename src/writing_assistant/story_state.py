"""Explicit, evidence-linked story state in immutable Creative Records.

Local caller acknowledgement is not service authentication. Machine extraction
can propose entries; only an already authorized user operation can establish or
change constraints/adopted facts. This module never changes World authorities.
"""

from contextlib import contextmanager
import fcntl
import os
import stat

from .core.errors import AssistantError, require
from .core.interface import IDENTIFIER, HASH
from .core.jsonio import canonical, decode, digest, fields
from .records.application import owner_store
from .records.core import RecordsError, ref_key

CONTRACT = "writing-assistant-story-state/1"
REQUEST_CONTRACT = "writing-assistant-story-state-request/1"
REVISION_CONTRACT = "writing-assistant-story-state-revision/1"
SELECTION_CONTRACT = "writing-assistant-story-state-selection/1"
MAX_ENTRIES = 128
MAX_REVISIONS = 256
MAX_STATE_BYTES = 131072
KINDS = frozenset({"knowledge", "location", "time", "resource", "relationship", "open-question", "purpose"})
STATUSES = frozenset({"user_constraint", "proposal", "adopted_fact"})


def _identifier(value):
    require(type(value) is str and IDENTIFIER.fullmatch(value), "invalid_identifier")
    return value


def _text(value, maximum=4096):
    require(type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= maximum,
            "invalid_story_state")


def _tags(value):
    require(type(value) is list and len(value) <= 16 and len(set(map(str, value))) == len(value),
            "invalid_story_tags")
    for tag in value:
        _identifier(tag)
    return value


def _ref(value, project_id):
    ref_key(value)
    require(value["project_id"] == project_id, "project_mismatch")
    return value


def _evidence(value, project_id, *, required=False):
    require(type(value) is list and len(value) <= 4 and (value or not required), "story_evidence_required")
    for item in value:
        fields(item, ("ref", "start", "end", "sha256"))
        _ref(item["ref"], project_id)
        require(type(item["start"]) is int and type(item["end"]) is int
                and 0 <= item["start"] < item["end"] <= 16777216
                and item["end"] - item["start"] <= 1048576,
                "invalid_story_evidence")
        require(type(item["sha256"]) is str and HASH.fullmatch(item["sha256"]), "invalid_story_evidence")
    return value


def _entry(value, project_id):
    fields(value, ("id", "kind", "subject", "value", "status", "origin", "evidence", "tags"))
    _identifier(value["id"])
    _text(value["subject"], 512)
    require(type(value["kind"]) is str and value["kind"] in KINDS
            and type(value["status"]) is str and value["status"] in STATUSES
            and value["origin"] in ("user", "generated"), "invalid_story_state")
    require(value["origin"] != "generated" or value["status"] == "proposal", "generated_fact_forbidden")
    _tags(value["tags"])
    _evidence(value["evidence"], project_id, required=value["status"] != "proposal")
    body, kind = value["value"], value["kind"]
    shape = {"knowledge": ("holder", "topic", "claim"), "location": ("entity", "place"),
             "time": ("event", "position"), "resource": ("holder", "resource", "amount", "unit"),
             "relationship": ("source", "target", "relation"),
             "open-question": ("question", "options", "resolution"),
             "purpose": ("chapter", "aim", "open_choices")}[kind]
    fields(body, shape)
    for key, item in body.items():
        if key == "amount":
            require(type(item) is int and -1000000000 <= item <= 1000000000, "invalid_story_resource")
        elif key == "chapter":
            require(type(item) is int and 0 <= item <= 20000, "invalid_story_purpose")
        elif key in {"options", "open_choices"}:
            require(type(item) is list and len(item) <= 8, "invalid_story_choices")
            for choice in item:
                _text(choice, 1024)
            require(len(set(item)) == len(item), "invalid_story_choices")
        elif key == "resolution" and item is None:
            pass
        else:
            _text(item)
    return value


def _slot(entry):
    body, kind = entry["value"], entry["kind"]
    secondary = {"knowledge": body.get("topic"), "resource": body.get("resource"),
                 "relationship": (body.get("target"), body.get("relation")),
                 "purpose": body.get("chapter"), "open-question": entry["id"]}.get(kind)
    return kind, entry["subject"], secondary


def _entries(value, project_id):
    require(type(value) is list and len(value) <= MAX_ENTRIES, "story_state_limit")
    ids, established = set(), {}
    for entry in value:
        _entry(entry, project_id)
        require(entry["id"] not in ids, "duplicate_story_entry")
        ids.add(entry["id"])
        if entry["status"] != "proposal":
            slot = _slot(entry)
            require(slot not in established or established[slot] == entry["value"], "conflicting_story_fact")
            established[slot] = entry["value"]
    require(len(canonical(value)) <= MAX_STATE_BYTES, "story_state_limit")
    require(len(_references(value)) <= 48, "story_state_evidence_limit")
    return value


def _references(entries, extra=()):
    unique = {}
    for item in [evidence["ref"] for entry in entries for evidence in entry["evidence"]] + list(extra):
        unique[canonical(item)] = item
    return list(unique.values())


def verify_evidence(store, scope, evidence):
    """Authenticate only explicit original versions and exact byte spans."""
    bodies = {}
    for item in evidence:
        _evidence([item], scope.project_id)
        key = canonical(item["ref"])
        if key not in bodies:
            bodies[key] = store.read(scope, item["ref"])["body"]
        raw = bodies[key]
        require(item["end"] <= len(raw)
                and digest(raw[item["start"]:item["end"]]) == item["sha256"], "stale_story_evidence")


def _operation(scope, state_id, revision):
    return "story-state-" + digest(canonical([scope.project_id, state_id, revision]))


@contextmanager
def _lock(store, scope, state_id):
    _identifier(state_id)
    caught = None
    with store.session(scope, write=True) as io:
        parts = tuple((store.project(scope) + "/story-state-locks").split("/"))
        parent = io.directory(parts, create=True)
        io._verify_dirs(parts)
        name = state_id + ".lock"
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        held = False
        try:
            row = os.fstat(fd)
            require(stat.S_ISREG(row.st_mode) and row.st_nlink == 1, "invalid_story_state_lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AssistantError("busy") from None
            held = True
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require((row.st_dev, row.st_ino) == (current.st_dev, current.st_ino), "invalid_story_state_lock")
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


def _snapshot(store, scope, reference):
    _ref(reference, scope.project_id)
    saved = store.read(scope, reference)
    value = decode(saved["body"])
    fields(value, ("contract", "project_id", "state_id", "revision", "previous", "request", "entries"))
    require(value["contract"] == CONTRACT and value["project_id"] == scope.project_id
            and saved["body"] == canonical(value), "invalid_story_state_snapshot")
    _identifier(value["state_id"])
    require(type(value["revision"]) is int and 0 <= value["revision"] < MAX_REVISIONS,
            "invalid_story_state_snapshot")
    require(saved["metadata"]["operation_id"] == _operation(scope, value["state_id"], value["revision"])
            and saved["metadata"]["parent"] == value["previous"]
            and (value["previous"] is None) == (value["revision"] == 0), "invalid_story_state_snapshot")
    _entries(value["entries"], scope.project_id)
    _normalize(value["request"], scope.project_id, revision=value["revision"] != 0)
    return value


def _chain(store, scope, state_id):
    _identifier(state_id)
    result, previous = [], None
    for revision in range(MAX_REVISIONS):
        saved = store.operation(scope, _operation(scope, state_id, revision))
        if saved is None:
            return result
        value = _snapshot(store, scope, saved["ref"])
        require(value["state_id"] == state_id and value["revision"] == revision
                and value["previous"] == previous, "invalid_story_state_chain")
        result.append((value, saved["ref"]))
        previous = saved["ref"]
    return result


def _normalize(value, project_id, *, revision=False):
    value = decode(canonical(value))
    if revision:
        fields(value, ("schema_version", "operation_id", "upsert", "remove", "reason", "evidence"))
        require(value["schema_version"] == REVISION_CONTRACT, "unsupported_story_state_version")
        _text(value["reason"], 4096)
        _evidence(value["evidence"], project_id)
        require(type(value["remove"]) is list and len(value["remove"]) <= MAX_ENTRIES,
                "invalid_story_state")
        for entry_id in value["remove"]:
            _identifier(entry_id)
        require(len(set(value["remove"])) == len(value["remove"]), "duplicate_story_entry")
        _entries(value["upsert"], project_id)
        require(not (set(value["remove"]) & {item["id"] for item in value["upsert"]}), "conflicting_story_update")
        require(bool(value["upsert"] or value["remove"]), "empty_story_update")
    else:
        fields(value, ("schema_version", "state_id", "project_id", "operation_id", "entries"))
        require(value["schema_version"] == REQUEST_CONTRACT, "unsupported_story_state_version")
        _identifier(value["state_id"])
        require(value["project_id"] == project_id, "project_mismatch")
        _entries(value["entries"], project_id)
    _identifier(value["operation_id"])
    return value


def _view(value, reference):
    return {"contract": CONTRACT, "state_id": value["state_id"], "revision": value["revision"],
            "reference": reference, "snapshot": value, "model_calls": 0,
            "world_facts_written": False}


def _write(store, scope, state_id, request, entries, previous, revision):
    require(revision < MAX_REVISIONS, "story_state_revision_limit")
    evidence = [item for entry in entries for item in entry["evidence"]] + request.get("evidence", [])
    verify_evidence(store, scope, evidence)
    value = {"contract": CONTRACT, "project_id": scope.project_id, "state_id": state_id,
             "revision": revision, "previous": previous, "request": request, "entries": entries}
    related = _references(entries, [item["ref"] for item in request.get("evidence", [])])
    reference = store.save(scope, operation_id=_operation(scope, state_id, revision), body=canonical(value),
                           title="Story state", kind="decision", parent=previous, related=related,
                           source={"authorship": "mixed", "origin": "Explicit local story state; no World authority"})["ref"]
    return _view(value, reference)


def create_in_store(store, scope, request, *, user_authorized=False):
    request = _normalize(request, scope.project_id)
    require(type(user_authorized) is bool, "invalid_user_acknowledgement")
    state_id = request["state_id"]
    with _lock(store, scope, state_id):
        existing = _chain(store, scope, state_id)
        if existing:
            value, reference = existing[0]
            require(value["request"] == request, "story_state_conflict")
            verify_evidence(store, scope, [item for entry in value["entries"] for item in entry["evidence"]])
            return _view(value, reference)
        require(user_authorized or all(item["status"] == "proposal" for item in request["entries"]),
                "user_story_authorization_required")
        return _write(store, scope, state_id, request, request["entries"], None, 0)


def create(project, request, *, user_authorized=False, artifact_resolver=None):
    store, scope = owner_store(project, write=True, resolver=artifact_resolver)
    return create_in_store(store, scope, request, user_authorized=user_authorized)


def revise_in_store(store, scope, state_id, request, *, expected_ref, user_authorized=False):
    _identifier(state_id)
    _ref(expected_ref, scope.project_id)
    request = _normalize(request, scope.project_id, revision=True)
    require(type(user_authorized) is bool, "invalid_user_acknowledgement")
    with _lock(store, scope, state_id):
        chain = _chain(store, scope, state_id)
        require(bool(chain), "story_state_not_found")
        for value, reference in chain:
            if value["request"]["operation_id"] == request["operation_id"]:
                require(value["revision"] > 0 and value["request"] == request
                        and value["previous"] == expected_ref, "story_state_operation_conflict")
                verify_evidence(store, scope, [item for entry in value["entries"] for item in entry["evidence"]]
                                + request["evidence"])
                return _view(value, reference)
        latest, reference = chain[-1]
        require(reference == expected_ref, "stale_story_state")
        entries = {entry["id"]: entry for entry in latest["entries"]}
        require(set(request["remove"]) <= set(entries), "story_entry_not_found")
        changed = set(request["remove"]) | {entry["id"] for entry in request["upsert"]}
        protected = any(entries[item]["status"] != "proposal" for item in changed if item in entries)
        proposed_fact = any(entry["status"] != "proposal" for entry in request["upsert"])
        require(user_authorized or not (protected or proposed_fact), "user_story_authorization_required")
        require(not (protected or proposed_fact) or bool(request["evidence"]), "story_evidence_required")
        for entry_id in request["remove"]:
            del entries[entry_id]
        for entry in request["upsert"]:
            entries[entry["id"]] = entry
        result = _entries(list(entries.values()), scope.project_id)
        return _write(store, scope, state_id, request, result, reference, latest["revision"] + 1)


def revise(project, state_id, request, *, expected_ref, user_authorized=False, artifact_resolver=None):
    store, scope = owner_store(project, write=True, resolver=artifact_resolver)
    return revise_in_store(store, scope, state_id, request, expected_ref=expected_ref,
                           user_authorized=user_authorized)


def inspect(project, state_id, *, reference=None, artifact_resolver=None):
    store, scope = owner_store(project, resolver=artifact_resolver)
    _identifier(state_id)
    if reference is None:
        chain = _chain(store, scope, state_id)
        require(bool(chain), "story_state_not_found")
        value, reference = chain[-1]
    else:
        value = _snapshot(store, scope, reference)
        require(value["state_id"] == state_id, "story_state_mismatch")
    verify_evidence(store, scope, [item for entry in value["entries"] for item in entry["evidence"]])
    result = _view(value, reference)
    result["current"] = store.operation(scope, _operation(scope, state_id, value["revision"] + 1)) is None
    return result


def select_in_store(store, scope, reference, *, entry_ids=None, tags=(), require_current=True):
    """Select a frozen snapshot without discovering any other story or library."""
    value = _snapshot(store, scope, reference)
    require(type(require_current) is bool, "invalid_story_selection")
    # A record subset cannot prove that an unseen successor is absent. An
    # explicit historical read may proceed without claiming currentness.
    require(scope.record_ids is None or not require_current, "story_state_current_unavailable")
    current = (store.operation(scope, _operation(scope, value["state_id"], value["revision"] + 1)) is None
               if scope.record_ids is None else None)
    require(current or not require_current, "stale_story_state")
    tags = _tags(list(tags))
    if entry_ids is not None:
        require(type(entry_ids) is list and len(entry_ids) <= MAX_ENTRIES, "invalid_story_selection")
        for entry_id in entry_ids:
            _identifier(entry_id)
        require(len(set(entry_ids)) == len(entry_ids), "duplicate_story_entry")
        require(set(entry_ids) <= {item["id"] for item in value["entries"]}, "story_entry_not_found")
    selected, excluded = [], []
    for entry in value["entries"]:
        if ((entry_ids is None or entry["id"] in entry_ids)
                and (not tags or bool(set(tags) & set(entry["tags"])))):
            selected.append(entry)
        else:
            excluded.append(entry["id"])
    verify_evidence(store, scope, [item for entry in selected for item in entry["evidence"]])
    if require_current:
        require(store.operation(scope, _operation(scope, value["state_id"], value["revision"] + 1)) is None,
                "stale_story_state")
    scope.verify(reference["record_id"])
    return {"contract": SELECTION_CONTRACT, "reference": dict(reference), "state_id": value["state_id"],
            "revision": value["revision"], "entries": selected, "excluded_entry_ids": excluded, "current": current}


def select(project, reference, *, entry_ids=None, tags=(), require_current=True, artifact_resolver=None):
    store, scope = owner_store(project, resolver=artifact_resolver)
    return select_in_store(store, scope, reference, entry_ids=entry_ids, tags=tags, require_current=require_current)
