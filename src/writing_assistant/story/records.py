"""Book-local Creative Records, bookmarks and explicit writing context."""
import argparse
import hashlib
import json
from pathlib import Path
from importlib.resources import files as package_files
import uuid

from .. import book

COMMANDS = {"records", "prepare", "config"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS writing_book_identity (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), book_id TEXT NOT NULL UNIQUE
);
INSERT OR IGNORE INTO writing_book_identity VALUES(1, lower(hex(randomblob(16))));
CREATE TABLE IF NOT EXISTS writing_settings (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), mode TEXT NOT NULL, sandbox INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS creative_records (
    sequence INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE, name TEXT NOT NULL, revision INTEGER NOT NULL,
    parent TEXT REFERENCES creative_records(ref), title TEXT NOT NULL, category TEXT NOT NULL,
    audience TEXT NOT NULL, authorship TEXT NOT NULL, origin TEXT NOT NULL, source TEXT NOT NULL,
    body BLOB NOT NULL, digest TEXT NOT NULL, operation TEXT NOT NULL UNIQUE, signature TEXT NOT NULL,
    UNIQUE(name,revision)
);
CREATE TABLE IF NOT EXISTS creative_bookmarks (
    name TEXT PRIMARY KEY, refs TEXT NOT NULL, stop INTEGER, baseline TEXT
);
"""
CATEGORIES = ("manuscript", "feedback", "research", "setting", "decision", "question", "other")
AUDIENCES = ("owner", "author", "reader")


def json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def nonempty(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty text.")
    return value


def settings(db):
    row = db.execute("SELECT mode,sandbox FROM writing_settings WHERE singleton=1").fetchone()
    return {"writing_mode": row[0] if row else "lotus", "world_sandbox": bool(row[1]) if row else True}


def put_record(db, *, name, body, operation, title, category, audience, authorship, origin, source, parent,
               allow_opaque=False):
    for field in (name, operation, title):
        nonempty(field)
    if len(origin) > 4096:
        raise ValueError("Origin attribution exceeds 4096 characters.")
    if not allow_opaque:
        body.decode("utf-8")
    digest = checksum(body)
    signature = checksum(json_bytes([name, digest, title, category, audience, authorship, origin, source, parent]))
    retry = db.execute("SELECT ref,signature FROM creative_records WHERE operation=?", (operation,)).fetchone()
    if retry:
        if retry["signature"] != signature:
            raise ValueError("The record operation already identifies different input.")
        return metadata(db, retry["ref"])
    previous = db.execute("SELECT ref,revision FROM creative_records WHERE name=? ORDER BY revision DESC LIMIT 1",
                          (name,)).fetchone()
    if parent != (previous["ref"] if previous else None):
        raise ValueError("Supply the current record ref as parent when creating a revision.")
    revision = previous["revision"] + 1 if previous else 1
    ref = uuid.uuid4().hex
    db.execute("""INSERT INTO creative_records
                  (ref,name,revision,parent,title,category,audience,authorship,origin,source,body,digest,operation,signature)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (ref, name, revision, parent, title, category, audience, authorship, origin, source, body,
                digest, operation, signature))
    return metadata(db, ref)


META = "ref,name,revision,parent,title,category,audience,authorship,origin,source,digest AS sha256"


def metadata(db, ref):
    row = db.execute("SELECT " + META + " FROM creative_records WHERE ref=?", (ref,)).fetchone()
    if row is None:
        raise ValueError("Record reference unavailable.")
    return dict(row)


def record_bytes(db, ref):
    row = db.execute("SELECT body,digest FROM creative_records WHERE ref=?", (ref,)).fetchone()
    if row is None:
        raise ValueError("Record reference unavailable.")
    if checksum(row["body"]) != row["digest"]:
        raise ValueError("Stored record digest mismatch.")
    return row["body"]


def material(db, ref, audiences=None):
    meta = metadata(db, ref)
    if audiences is not None and meta["audience"] not in audiences:
        raise ValueError("Record audience is outside the selected context.")
    try:
        text = record_bytes(db, ref).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("This record has an opaque payload and cannot enter a text context.") from exc
    return {"ref": ref, "category": meta["category"], "sha256": meta["sha256"], "text": text}


def scoped_read(db, ref, permit):
    """A trusted host rechecks its exact book/ref grant on every consumer read."""
    book_id = db.execute("SELECT book_id FROM writing_book_identity WHERE singleton=1").fetchone()[0]
    if permit(book_id, ref) is not True:
        raise ValueError("Record reference unavailable.")
    return record_bytes(db, ref)


def bounded(payload, size):
    if len(json_bytes(payload)) > size:
        raise ValueError("Context exceeds the selected byte budget.")
    return payload


def amount(value):
    number = int(value)
    if not 1 <= number <= 2**63-1:
        raise argparse.ArgumentTypeError("Expected a positive 64-bit integer.")
    return number


def register(subs):
    p = subs.add_parser("config", help="inspect or change independent writing and sandbox settings")
    p.add_argument("--writing-mode", choices=("direct", "lotus"))
    p.add_argument("--world-sandbox", choices=("on", "off"))
    p = subs.add_parser("prepare", help="prepare a writing or review packet without execution")
    p.add_argument("request")
    p.add_argument("--phase", choices=("draft", "plan-book", "plan-scene", "revise", "reader-review", "continuity-review"),
                   default="draft")
    p.add_argument("--target", type=amount, help="chapter to be written or reviewed")
    p.add_argument("--chapter", nargs=2, type=amount, metavar=("NUMBER", "REVISION"))
    p.add_argument("--prior", nargs=2, type=amount, action="append", default=[], metavar=("NUMBER", "REVISION"))
    p.add_argument("--material", action="append", default=[], metavar="REF")
    p.add_argument("--max-bytes", type=amount, default=262144)
    p = subs.add_parser("records", help="store and select versioned creative material")
    sub = p.add_subparsers(dest="records_action", required=True)
    p = sub.add_parser("save")
    p.add_argument("name")
    body = p.add_mutually_exclusive_group(required=True)
    body.add_argument("--file", type=Path, help="read the record body from a prepared UTF-8 file")
    body.add_argument("--stdin", action="store_true", help="read the prepared record text from standard input")
    p.add_argument("--operation", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--category", choices=CATEGORIES, required=True)
    p.add_argument("--audience", choices=AUDIENCES, default="owner")
    p.add_argument("--authorship", choices=("user", "agent", "mixed", "unknown"), default="unknown")
    p.add_argument("--origin", default="")
    p.add_argument("--source", default="", help="descriptive provenance for this saved copy")
    p.add_argument("--parent", help="exact parent ref when revising")
    sub.add_parser("read").add_argument("ref")
    sub.add_parser("history").add_argument("name")
    for operation in ("recent", "search"):
        p = sub.add_parser(operation)
        if operation == "search":
            p.add_argument("term")
        p.add_argument("--category", choices=CATEGORIES)
        p.add_argument("--limit", type=amount, default=40)
        p.add_argument("--after", type=amount, help="older than this sequence")
    p = sub.add_parser("bookmark")
    p.add_argument("name")
    p.add_argument("--ref", action="append", required=True)
    p.add_argument("--stop", type=int, help="Unicode character offset in the last selected record")
    p.add_argument("--baseline", help="current version token from the selected producer")
    p = sub.add_parser("context")
    p.add_argument("name")
    p.add_argument("--baseline", help="current producer version, required for a baseline-bound bookmark")
    p.add_argument("--max-bytes", type=amount, default=262144)


def writable(args):
    if args.command == "config":
        return args.writing_mode is not None or args.world_sandbox is not None
    return args.command == "records" and args.records_action in ("save", "bookmark")


def prepare(db, args):
    config = settings(db)
    phase = args.phase
    nonempty(args.request)
    if phase in ("plan-scene", "revise") and config["writing_mode"] != "lotus":
        raise ValueError("This phase requires Lotus writing mode.")
    if phase in ("reader-review", "continuity-review", "revise") and not args.chapter:
        raise ValueError("This phase requires an exact current draft.")
    prior_numbers = [number for number, _ in args.prior]
    if prior_numbers != sorted(set(prior_numbers)):
        raise ValueError("Select earlier chapters once each, in narrative order.")
    if len(args.material) != len(set(args.material)):
        raise ValueError("Duplicate preparation material.")
    target = getattr(args, "target", None)
    if args.chapter:
        if target is not None and target != args.chapter[0]:
            raise ValueError("Target chapter differs from the selected draft.")
        target = args.chapter[0]
    if target is not None and any(n >= target for n, _ in args.prior):
        raise ValueError("Prior chapters must precede the current draft.")
    if phase == "reader-review" and args.material:
        raise ValueError("Reader review accepts only the selected manuscript and earlier prose.")
    items = []
    for role, refs in (("prior-prose", args.prior), ("current-draft", [args.chapter] if args.chapter else [])):
        for n, rev in refs:
            row = book.chapter(db, n, rev)
            items.append({"role": role, "chapter": n, "revision": rev, "sha256": row["digest"],
                          "text": row["body"].decode("utf-8")})
    for ref in args.material:
        meta = metadata(db, ref)
        if phase == "continuity-review" and meta["category"] != "setting":
            raise ValueError("A continuity review accepts only selected setting records alongside prose.")
        items.append({"role": "record", **material(db, ref, {"author", "reader"})})
    if phase == "revise" and not any(i.get("category") == "feedback" for i in items):
        raise ValueError("Revision requires a selected feedback record.")
    instructions = []
    if phase == "plan-book":
        template = package_files("writing_assistant").joinpath("resources", "templates", "book", "opening-brief.md")
        if not template.is_file():
            template = Path(__file__).resolve().parents[3] / "templates/book/opening-brief.md"
        instructions.append(template.read_text(encoding="utf-8"))
        if config["writing_mode"] == "lotus":
            instructions.append("Use the volume and turning-point outline to explore the opening volume's central choice.")
    elif config["writing_mode"] == "lotus" and phase in ("draft", "plan-scene", "revise"):
        instructions = ["Develop the current choice from the protagonist's desire and its consequences.",
                        "Use the nine-cell outline at volume scale and at significant turns."]
    book_id = db.execute("SELECT book_id FROM writing_book_identity WHERE singleton=1").fetchone()[0]
    payload = {"format": "writing-assistant/preparation/1", "book_id": book_id, "status": "prepared-unexecuted", "phase": phase,
               "request": args.request, "target_chapter": target, "materials": items, "settings": config, "instructions": instructions}
    payload["sha256"] = checksum(json_bytes(payload))
    return bounded(payload, args.max_bytes)


def list_records(db, args):
    searching = args.records_action == "search"
    term = nonempty(args.term).casefold() if searching else None
    q = "SELECT sequence," + META + " FROM creative_records c WHERE (? IS NULL OR category=?)"
    if not searching:
        q += " AND revision=(SELECT max(v.revision) FROM creative_records v WHERE v.name=c.name)"
    q += " AND (? IS NULL OR sequence<?) ORDER BY sequence DESC"
    items = []
    for row in db.execute(q, (args.category, args.category, args.after, args.after)):
        info = dict(row)
        if searching and term not in info["title"].casefold():
            raw = record_bytes(db, info["ref"])
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if term not in content.casefold():
                continue
        if len(items) == args.limit:
            return {"items": items, "next_after": items[-1]["sequence"]}
        items.append(info)
    return {"items": items, "next_after": None}


def run(db, args):
    if args.command == "config":
        current = settings(db)
        if writable(args):
            mode = args.writing_mode or current["writing_mode"]
            sandbox = current["world_sandbox"] if args.world_sandbox is None else args.world_sandbox == "on"
            db.execute("INSERT OR REPLACE INTO writing_settings VALUES(1,?,?)", (mode, int(sandbox)))
        return settings(db)
    if args.command == "prepare":
        return prepare(db, args)
    action = args.records_action
    if action == "save":
        return put_record(db, name=args.name, body=args.record_body, operation=args.operation,
                          title=args.title, category=args.category, audience=args.audience,
                          authorship=args.authorship, origin=args.origin, source=args.source, parent=args.parent)
    if action == "read":
        return record_bytes(db, args.ref)
    if action == "history":
        rows = db.execute("SELECT " + META + " FROM creative_records WHERE name=? ORDER BY revision", (args.name,))
        return [dict(row) for row in rows]
    if action in ("recent", "search"):
        return list_records(db, args)
    if action == "bookmark":
        nonempty(args.name)
        if len(set(args.ref)) != len(args.ref):
            raise ValueError("A bookmark contains duplicate refs.")
        for ref in args.ref:
            metadata(db, ref)
        if args.stop is not None and not 0 <= args.stop <= len(record_bytes(db, args.ref[-1]).decode("utf-8")):
            raise ValueError("Stop offset is outside the last selected record.")
        db.execute("INSERT OR REPLACE INTO creative_bookmarks VALUES(?,?,?,?)",
                   (args.name, json.dumps(args.ref), args.stop, args.baseline))
        return {"name": args.name, "refs": args.ref, "stop": args.stop}
    row = db.execute("SELECT refs,stop,baseline FROM creative_bookmarks WHERE name=?", (args.name,)).fetchone()
    if row is None:
        raise ValueError("Bookmark not found.")
    if row["baseline"] != args.baseline:
        raise ValueError("Bookmark baseline differs from the current producer token.")
    return bounded({"name": args.name, "stop": row["stop"],
                    "materials": [material(db, r) for r in json.loads(row["refs"])]}, args.max_bytes)
