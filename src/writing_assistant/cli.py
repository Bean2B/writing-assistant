"""Command-line interface for a single local book."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import subprocess
import zipfile

from . import __version__, book, writing_test
from .operations import backup, engineering, host
from .research import library
from .story import chapter_cards
from .runtime import tasks, world_adapter
from .features import BOOK_FEATURES


def positive(text):
    value = int(text)
    if not 1 <= value <= 2**63 - 1:
        raise argparse.ArgumentTypeError("expected a positive 64-bit integer")
    return value


def arguments(argv):
    parser = argparse.ArgumentParser(prog="writing-assistant", description="Work with one local book.")
    parser.add_argument("--version", action="version", version=f"Writing Assistant {__version__}")
    parser.add_argument("--book", type=Path, metavar="DIR", help="directory containing book.sqlite3")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("init", help="create an empty book").add_argument("title")
    p = subs.add_parser("import-chapter", aliases=["import-test"],
                        help="import a historical chapter and its reading evidence into its book")
    p.add_argument("case", type=Path)
    p.add_argument("--manuscript-only", action="store_true",
                   help="import only manuscript bytes, leaving existing book records intact")
    subs.add_parser("status", help="show chapter revisions, adoption and reader counts")
    p = subs.add_parser("reader", help="look up a book's reader or save the session handle returned by the host")
    p.add_argument("name")
    p.add_argument("--handle")
    p = subs.add_parser("save", help="save an immutable chapter revision")
    p.add_argument("number", type=positive)
    p.add_argument("--file", type=Path, help="UTF-8 manuscript, or stdin when omitted")
    p.add_argument("--card", type=Path, help="save author card JSON with the manuscript in one transaction")
    p = subs.add_parser("chapter", help="inspect a chapter dossier or attach author card JSON to an exact revision")
    p.add_argument("number", type=positive)
    p.add_argument("--revision", type=positive)
    p.add_argument("--card", type=Path, help="attach JSON from a file, or - for stdin")
    p.add_argument("--parent-version", type=positive, help="current card version when revising its contents")
    p.add_argument("--card-version", type=positive, help="read a historical version of this revision's card")
    p = subs.add_parser("read", help="emit only the exact manuscript bytes")
    p.add_argument("number", type=positive)
    p.add_argument("--revision", type=positive)
    for name, help_text in [("adopt", "mark the user-selected revision as adopted"),
                            ("reviews", "show original feedback for a specific revision")]:
        p = subs.add_parser(name, help=help_text)
        p.add_argument("number", type=positive)
        p.add_argument("--revision", type=positive, required=True)
        if name == "reviews":
            p.add_argument("--reader", help="show only this reader’s own response")
    p = subs.add_parser("packet", help="prepare a fixed manuscript for a registered reader session")
    p.add_argument("number", type=positive)
    p.add_argument("--revision", type=positive, required=True)
    p.add_argument("--reader", required=True)
    p = subs.add_parser("note", help="record a fact, intention, open question or intentional omission")
    p.add_argument("kind", choices=["fact", "intent", "open", "hold"])
    p.add_argument("detail")
    p.add_argument("--chapter", type=positive)
    p.add_argument("--revision", type=positive)
    p.add_argument("--quote")
    subs.add_parser("close-note", help="retire a note from future handoffs").add_argument("id", type=positive)
    subs.add_parser("context", help="author-only handoff for the next chapter").add_argument("number", type=positive)
    p = subs.add_parser("recall", help="find earlier passages in this book")
    p.add_argument("--before", type=positive, required=True)
    p.add_argument("terms", nargs="+")
    p = subs.add_parser("feedback", help="record a reader's unedited response to a fixed manuscript")
    p.add_argument("--packet", required=True, help="book-local packet id")
    p.add_argument("--sha256", required=True, help="digest of the manuscript sent")
    p.add_argument("--file", type=Path, help="UTF-8 response, or stdin when omitted")
    subs.add_parser("upgrade", help="upgrade an existing local book in one transaction")
    subs.add_parser("doctor", help="report local runtime capabilities without model calls")
    for retired in ("merge", "queue", "closeout"):
        subs.add_parser(retired, help="report retired cloud operation")
    for module in (*BOOK_FEATURES, tasks, world_adapter, library, host, engineering, backup):
        module.register(subs)
    return parser.parse_args(argv)


def input_bytes(path):
    return path.read_bytes() if path else sys.stdin.buffer.read()


def run(db, args):
    cmd = args.command
    if cmd == "save":
        result = book.save(db, args.number, input_bytes(args.file))
        if args.card is not None:
            result["card_version"] = chapter_cards.store(db, args.number, result["revision"], args.card_data, None)
        else:
            result["card_version"] = book.current_card_version(db, args.number, result["revision"])
        return result
    if cmd == "chapter":
        if args.card is not None:
            chapter_cards.store(db, args.number, args.revision, args.card_data, args.parent_version)
        return chapter_cards.overview(db, args.number, args.revision, args.card_version)
    if cmd == "reader":
        name = args.name.strip()
        if not name or (args.handle is not None and not args.handle.strip()):
            raise ValueError("Reader name and session handle must be nonempty.")
        if args.handle is not None:
            handle = args.handle.strip()
            if db.execute("SELECT 1 FROM packets WHERE handle=? AND reader<>?", (handle, name)).fetchone():
                raise ValueError("This session was used for another reader.")
            db.execute("INSERT INTO readers VALUES(?,?) ON CONFLICT(name) DO UPDATE SET handle=excluded.handle",
                       (name, handle))
        row = db.execute("SELECT handle FROM readers WHERE name=?", (name,)).fetchone()
        return {"reader": name, "handle": row[0] if row else None}
    if cmd == "read":
        return book.chapter(db, args.number, args.revision)["body"]
    if cmd == "note":
        return book.add_note(db, args.kind, args.detail, args.chapter, args.revision, args.quote)
    if cmd == "close-note":
        if not db.execute("UPDATE notes SET closed=1 WHERE id=?", (args.id,)).rowcount:
            raise ValueError("Note not found.")
        return {"closed": args.id}
    if cmd == "context":
        return book.handoff(db, args.number)
    if cmd == "recall":
        return book.recall(db, args.before, args.terms)
    if cmd == "packet":
        return book.packet(db, args.number, args.revision, args.reader)
    if cmd == "feedback":
        return book.feedback(db, args.packet, args.sha256, input_bytes(args.file))
    if cmd == "reviews":
        shelf = book.chapter(db, args.number, args.revision)
        rows = db.execute("""SELECT reader,response,origin FROM feedback WHERE number=? AND revision=?
                             AND (? IS NULL OR reader=?) ORDER BY reader""",
                          (args.number, args.revision, args.reader, args.reader))
        return {"number": args.number, "revision": args.revision, "sha256": shelf["digest"],
                "reviews": [{"reader": r[0], "response": r[1].decode("utf-8"), "origin": r[2]} for r in rows]}
    if cmd == "adopt":
        book.chapter(db, args.number, args.revision)
        db.execute("INSERT INTO adopted VALUES(?,?) ON CONFLICT(number) DO UPDATE SET revision=excluded.revision",
                   (args.number, args.revision))
        return {"adopted": args.number, "revision": args.revision}
    version_column = "NULL"
    if db.execute("PRAGMA user_version").fetchone()[0] >= 4:
        version_column = "(SELECT max(version) FROM chapter_cards WHERE number=c.number AND revision=c.revision)"
    rows = db.execute(f"""
        SELECT c.number, c.revision, c.digest AS sha256, (a.revision IS c.revision) AS adopted,
               {version_column} AS card_version,
               (SELECT count(*) FROM feedback f WHERE f.number=c.number AND f.revision=c.revision) AS readers
        FROM chapters c LEFT JOIN adopted a ON c.number=a.number ORDER BY c.number,c.revision
    """)
    return {**dict(db.execute("SELECT * FROM book").fetchone()), "chapters": [dict(row) for row in rows]}


def main(argv=None):
    args = arguments(argv)
    try:
        if args.command == "doctor":
            result = {"product": "Writing Assistant", "version": __version__, "schema": book.SCHEMA_VERSION,
                      "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                      "provider_calls": 0, "features": sorted({c for module in BOOK_FEATURES for c in module.COMMANDS}
                                         | tasks.COMMANDS | world_adapter.COMMANDS | {"chapter", "host", "library", "backup", "restore", "engineering"})}
        elif args.command in {"merge", "queue", "closeout"}:
            result = {"command": args.command, "status": "retired", "dispatched": False}
        elif args.command == "engineering":
            result = engineering.execute(args)
        elif args.command == "host":
            result = host.execute(args)
        elif args.command == "library":
            result = library.execute(args)
        elif args.book is None:
            raise ValueError("Select a book directory with --book DIR.")
        elif args.command in {"backup", "restore"}:
            result = backup.execute(args)
        elif args.command in world_adapter.COMMANDS:
            result = world_adapter.execute(args)
        elif args.command in tasks.COMMANDS:
            result = tasks.execute(args)
        elif args.command == "init":
            with book.new_book(args.book, args.title):
                pass
            result = {"title": args.title, "book": str(args.book),
                      "planning_hint": "For new fiction, use prepare REQUEST --phase plan-book."}
        elif args.command in {"import-chapter", "import-test"}:
            result = writing_test.load(args.book, args.case, args.manuscript_only)
        else:
            if args.command == "chapter":
                if args.card is not None and (args.revision is None or args.card_version is not None):
                    raise ValueError("Attach a card with --revision and omit --card-version.")
                if args.parent_version is not None and args.card is None:
                    raise ValueError("--parent-version is for updating a card.")
            if args.command in {"chapter", "save"} and args.card is not None:
                if args.card == Path("-") and args.command == "save" and args.file is None:
                    raise ValueError("Supply --file for the manuscript when the card uses stdin.")
                args.card_data = json.loads(input_bytes(None if args.card == Path("-") else args.card))
            if args.command == "records" and args.records_action == "save":
                args.record_body = input_bytes(args.file)
                if args.stdin:
                    book.text_bytes(args.record_body)
            write = args.command in {"save", "note", "close-note", "feedback", "adopt", "packet"} or (
                args.command == "reader" and args.handle is not None) or (args.command == "chapter" and args.card is not None)
            feature = next((module for module in BOOK_FEATURES if args.command in module.COMMANDS), None)
            write = feature.writable(args) if feature else write or args.command == "upgrade"
            with closing(book.connect(args.book, write)) as db, db:
                if feature:
                    if db.execute("PRAGMA user_version").fetchone()[0] < 3:
                        raise ValueError("This feature needs an upgraded book. Run upgrade first.")
                    result = feature.run(db, args)
                elif args.command == "upgrade":
                    result = {"schema": book.SCHEMA_VERSION}
                else:
                    result = run(db, args)
        if isinstance(result, bytes):
            sys.stdout.buffer.write(result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return tasks.exit_status(args, result) or world_adapter.exit_status(args, result)
