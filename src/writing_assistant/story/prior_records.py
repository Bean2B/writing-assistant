"""Import one user-selected inline Creative Records version from its owner export."""
import base64
import json
from pathlib import Path
import re

from . import records


COMMANDS = {"import-record"}
SCHEMA = ""
BODY_LIMIT = 16 * 1024 * 1024
METADATA_LIMIT = 1024 * 1024
REF_FIELDS = {"contract", "project_id", "record_id", "version_id", "sha256"}
METADATA_FIELDS = {"contract", "project_id", "record_id", "version_id", "operation_id", "title", "kind",
                   "work_id", "source", "audiences", "original_created_at", "received_at", "parent", "related", "body"}
OLD_KINDS = {"idea", "fragment", "draft", "setting", "decision", "feedback", "prose"}


def register(subs):
    p = subs.add_parser("import-record", help="save one explicitly selected prior Creative Records version")
    p.add_argument("--selection", type=Path, required=True, help="prior exact ref or unchanged save receipt")
    p.add_argument("--export", type=Path, required=True, help="prior owner CLI JSON from records show --ref")
    p.add_argument("--export-sha256", required=True, help="trusted digest of the complete selected export")
    p.add_argument("--category", required=True, choices=records.CATEGORIES)
    p.add_argument("--audience", default="owner", choices=records.AUDIENCES)


def writable(args):
    return True


def _read(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Selected Creative Records input exceeds its size limit.")
    return raw


def _decode(raw):
    def pairs(items):
        result = dict(items)
        if len(result) != len(items):
            raise ValueError("Duplicate field in prior Creative Records input.")
        return result
    def reject(_):
        raise ValueError("Invalid number in prior Creative Records input.")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except RecursionError:
        raise ValueError("Prior Creative Records input exceeds the supported nesting depth.") from None


def _fields(value, keys):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Unexpected prior Creative Records object.")


def _ref(ref):
    _fields(ref, REF_FIELDS)
    if (ref["contract"] != "creative-records/1" or not isinstance(ref["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])):
        raise ValueError("Unsupported or invalid selected reference.")
    for key in ("project_id", "record_id", "version_id"):
        if not _identifier(ref[key]):
            raise ValueError("Invalid prior project, record or version identity.")
    return ref


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", value)


def _selected(path):
    selected = _decode(_read(path, METADATA_LIMIT))
    if isinstance(selected, dict) and set(selected) == {"status", "ref"} and selected["status"] in ("created", "retry"):
        selected = selected["ref"]
    return _ref(selected)


def _validate(meta, selected, audience):
    _fields(meta, METADATA_FIELDS)
    _fields(meta["body"], {"reference", "storage", "sha256", "size"})
    if any(meta[k] != selected[k] for k in REF_FIELDS - {"sha256"}) or meta["body"]["sha256"] != selected["sha256"]:
        raise ValueError("Export metadata differs from the selected original.")
    if meta["body"]["storage"] != "inline" or meta["body"]["reference"] is not None:
        raise ValueError("Reference-backed originals require live producer authority. Select an authorized inline export.")
    if (type(meta["body"]["size"]) is not int or not 0 <= meta["body"]["size"] <= BODY_LIMIT
            or not isinstance(meta["audiences"], list) or not all(_identifier(a) for a in meta["audiences"])
            or audience not in meta["audiences"] or "owner" not in meta["audiences"]):
        raise ValueError("Unsupported size or audience for this prior owner export.")
    author = meta["source"]
    _fields(author, {"authorship", "origin"})
    origin = author["origin"]
    if (author["authorship"] not in ("user", "agent", "mixed", "unknown")
            or (origin is not None and (not isinstance(origin, str) or len(origin) > 4096))
            or not isinstance(meta["title"], str) or len(meta["title"]) > 4096
            or not isinstance(meta["kind"], str) or meta["kind"] not in OLD_KINDS
            or not _identifier(meta["operation_id"])):
        raise ValueError("Invalid prior Creative Records metadata.")
    old_id = records.checksum(records.json_bytes([selected["project_id"], meta["operation_id"]]) + b"\n")
    if selected["version_id"] != "v-" + old_id:
        raise ValueError("Prior version identity does not match its project and operation.")
    if meta["parent"] is None:
        if selected["record_id"] != "r-" + old_id:
            raise ValueError("Prior root record identity does not match its operation.")
    else:
        parent = _ref(meta["parent"])
        if parent["project_id"] != selected["project_id"] or parent["record_id"] != selected["record_id"]:
            raise ValueError("Prior parent reference is inconsistent.")
    if not isinstance(meta["related"], list) or len(meta["related"]) > 64:
        raise ValueError("Invalid projected prior relations.")
    for edge in meta["related"]:
        if _ref(edge)["project_id"] != selected["project_id"]:
            raise ValueError("Prior relation crosses project scope.")


def run(db, args):
    selected = _selected(args.selection)
    raw = _read(args.export, (BODY_LIMIT + 2) // 3 * 4 + 2 * METADATA_LIMIT)
    if records.checksum(raw) != args.export_sha256:
        raise ValueError("Complete export digest differs from the selected file.")
    exported = _decode(raw)
    _fields(exported, {"ref", "metadata", "body_base64"})
    if _ref(exported["ref"]) != selected:
        raise ValueError("Export does not contain the selected project, record and version.")
    meta = exported["metadata"]
    _validate(meta, selected, args.audience)
    if not isinstance(exported["body_base64"], str):
        raise ValueError("Invalid prior record payload.")
    body = base64.b64decode(exported["body_base64"], validate=True)
    if len(body) != meta["body"]["size"] or records.checksum(body) != selected["sha256"]:
        raise ValueError("Decoded prior record body differs from the selected size or digest.")
    identity = "/".join(selected[k] for k in ("project_id", "record_id", "version_id"))
    # A projected old parent is provenance. Importing one version never creates its ancestors.
    provenance = {"format": "writing-assistant/prior-record/1", "selected": selected,
                  "export_sha256": args.export_sha256, "metadata": meta}
    source = meta["source"]
    return records.put_record(db, name="prior/" + identity, body=body, operation="import/" + identity,
                              title=meta["title"] if meta["title"].strip() else selected["record_id"],
                              category=args.category, audience=args.audience,
                              authorship=source["authorship"], origin=source["origin"] or "",
                              source=records.json_bytes(provenance).decode(), parent=None, allow_opaque=True)
