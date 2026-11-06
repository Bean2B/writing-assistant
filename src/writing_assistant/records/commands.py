"""Unified local owner commands over the sole Creative Records contracts."""

from dataclasses import dataclass
import base64
from pathlib import Path

from ..core.files import atomic, read
from ..core.jsonio import decode
from .application import artifact_resolver, owner_store
from .core import BODY_LIMIT, keys, require


@dataclass(frozen=True)
class RawOutput:
    body: bytes


def json_file(value):
    path = Path(value).absolute()
    return decode(read(path.parent, path.name, limit=1024 * 1024))


def reference_file(value, key="ref"):
    data = json_file(value)
    if isinstance(data, dict) and set(data) == {"status", key} and data["status"] in ("created", "retry"):
        return data[key]
    return data


def extend_parser(records, operation):
    records.add_argument("--artifacts-root", help="Explicit producer-file root; use with --bindings on every reference read")
    records.add_argument("--bindings", help="Explicit descriptor/project/audience/path bindings; no automatic lookup")
    operation.add_parser("bind-record-routes", help="Explicit local owner binding for legacy record-subset reads; preserves originals")
    listing = operation.choices["list"]
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--cursor")
    listing.add_argument("--max-bytes", type=int, default=32768)
    listing.add_argument("--scan-limit", type=int, default=100,
                         help="Inspect at most this many version entries per page (1-2000); follow next_cursor even after an empty page")
    for name in ("recent", "search"):
        command = operation.add_parser(name, help="List latest records" if name == "recent" else "Find literal Unicode text across stored versions")
        if name == "search":
            command.add_argument("keyword")
        command.add_argument("--work")
        command.add_argument("--all-versions", action="store_true")
        command.add_argument("--limit", type=int, default=20)
        command.add_argument("--cursor")
        command.add_argument("--max-bytes", type=int, default=32768,
                             help="Bound complete compact UTF-8 JSON including newline (1-16777216); follow next_cursor for remaining items")
        command.add_argument("--ignore-case", action="store_true")
        if name == "search":
            command.add_argument("--scan-limit", type=int, default=100,
                                 help="Inspect at most this many source versions per page (1-2000); total stays unknown")
    show = operation.add_parser("show", help="Inspect one exact version or return its original bytes")
    show.add_argument("--ref", required=True)
    show.add_argument("--raw", action="store_true")
    history = operation.add_parser("history", help="Page a checked linear version chain; verify the returned page's original bodies")
    history.add_argument("--record", required=True)
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--cursor")
    history.add_argument("--max-bytes", type=int, default=32768)
    bookmark = operation.add_parser("bookmark", help="Save explicit continuation selection without generation")
    bookmark.add_argument("--operation-id", "--operation", dest="operation_id", required=True)
    bookmark.add_argument("--request", required=True)
    operation.add_parser("read-bookmark").add_argument("--bookmark", required=True)
    context = operation.add_parser("context", help="Revalidate and prepare a bounded continuation bundle; no model call")
    selection = context.add_mutually_exclusive_group(required=True)
    selection.add_argument("--bookmark", help="Explicit exact saved bookmark reference file")
    selection.add_argument("--latest-bookmark", action="store_true",
                           help="Full owner: use the latest saved bookmark; never select a newer record version")
    context.add_argument("--max-bytes", type=int, default=262144)
    context.add_argument("--baseline")
    bookmarks = operation.add_parser("bookmarks", help="Full owner: discover recent exact bookmark selections without prose")
    bookmarks.add_argument("--limit", type=int, default=20, help="Return newest saved bookmarks (1-200); all are checked")
    bookmarks.add_argument("--max-bytes", type=int, default=32768, help="Bound complete UTF-8 JSON including newline (1-16777216)")
    for name in ("import-writer", "import-actor"):
        command = operation.add_parser(name, help="Reference explicitly supplied producer output without copying its body")
        command.add_argument("--operation-id", "--operation", dest="operation_id", required=True)
        command.add_argument("--descriptor", required=True)
        command.add_argument("--title", default="")
        command.add_argument("--work")
        if name == "import-writer":
            command.add_argument("--envelope", required=True, help="Original producer v1 envelope; outer provenance artifacts are not accepted")
            command.add_argument("--parent-ref")
        else:
            command.add_argument("--actor", required=True)
            command.add_argument("--source-version", required=True)


def execute(args):
    writing = args.record_command in ("save", "rebuild-index", "bind-record-routes", "bookmark", "import-writer", "import-actor")
    require(bool(args.artifacts_root) == bool(args.bindings), "invalid_request")
    resolver = artifact_resolver(args.artifacts_root, json_file(args.bindings)) if args.bindings else None
    store, scope = owner_store(args.project, write=writing, resolver=resolver)
    if args.record_command == "save":
        file = Path(args.file).absolute()
        return store.save(scope, operation_id=args.operation_id,
                          body=read(file.parent, file.name, limit=BODY_LIMIT),
                          title=args.title, kind=args.kind, work_id=args.work,
                          parent=reference_file(args.parent_ref) if args.parent_ref else None,
                          source={"authorship": args.authorship, "origin": args.origin})
    if args.record_command in ("read", "show"):
        found = store.read(scope, reference_file(args.reference_file if args.record_command == "read" else args.ref))
        if args.record_command == "show":
            if args.raw:
                return RawOutput(found["body"])
            return {"ref": found["ref"], "metadata": found["metadata"],
                    "body_base64": base64.b64encode(found["body"]).decode("ascii")}
        output = Path(args.output).absolute()
        atomic(output.parent, output.name, found["body"], exclusive=True, limit=BODY_LIMIT)
        return {"status": "saved-original", "ref": found["ref"]}
    if args.record_command == "list":
        from .query import list_metadata
        return list_metadata(store, scope, limit=args.limit, cursor=args.cursor,
                             max_bytes=args.max_bytes, scan_limit=args.scan_limit)
    if args.record_command == "rebuild-index":
        return store.rebuild_index(scope)
    if args.record_command == "bind-record-routes":
        return store.bind_record_routes(scope)
    if args.record_command in ("recent", "search"):
        from .query import list_records
        return list_records(store, scope, keyword=getattr(args, "keyword", None), work_id=args.work,
                            all_versions=args.all_versions or args.record_command == "search",
                            limit=args.limit, cursor=args.cursor, case_sensitive=not args.ignore_case,
                            max_bytes=args.max_bytes, scan_limit=getattr(args, "scan_limit", None))
    if args.record_command == "history":
        from .query import history
        return history(store, scope, args.record, limit=args.limit, cursor=args.cursor, max_bytes=args.max_bytes)
    if args.record_command == "bookmark":
        from .continuation import save_bookmark
        request = json_file(args.request)
        require(isinstance(request, dict) and "selected" in request and not
                (set(request) - {"selected", "stop", "decisions", "questions", "materials", "baseline"}), "invalid_schema")
        return save_bookmark(store, scope, operation_id=args.operation_id, **request)
    if args.record_command == "bookmarks":
        from .continuation import list_bookmarks
        return list_bookmarks(store, scope, limit=args.limit, max_bytes=args.max_bytes)
    if args.record_command in ("read-bookmark", "context"):
        from .continuation import prepare_context, prepare_latest_context, read_bookmark
        if args.record_command == "context" and args.latest_bookmark:
            return prepare_latest_context(store, scope, max_bytes=args.max_bytes, baseline=args.baseline)
        bookmark = reference_file(args.bookmark, "bookmark")
        if args.record_command == "read-bookmark":
            return read_bookmark(store, scope, bookmark)
        return prepare_context(store, scope, bookmark, max_bytes=args.max_bytes, baseline=args.baseline)
    if args.record_command == "import-writer":
        from .adapters import register_writer_output
        return register_writer_output(store, scope, operation_id=args.operation_id,
                                      envelope=json_file(args.envelope), reference=json_file(args.descriptor),
                                      title=args.title, work_id=args.work,
                                      parent=reference_file(args.parent_ref) if args.parent_ref else None)
    if args.record_command == "import-actor":
        from .adapters import register_actor_projection
        return register_actor_projection(store, scope, operation_id=args.operation_id,
                                         reference=json_file(args.descriptor), actor_id=args.actor,
                                         source_version=args.source_version, title=args.title, work_id=args.work)
    require(False, "invalid_request")
