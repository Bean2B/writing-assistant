"""A local book with immutable chapter revisions and source-linked author notes."""
from contextlib import contextmanager
import hashlib
import os
import re
import sqlite3
import tempfile
import uuid


SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE book (title TEXT NOT NULL, first_chapter INTEGER NOT NULL, source_case TEXT);
CREATE TABLE readers (name TEXT PRIMARY KEY, handle TEXT UNIQUE);
CREATE TABLE chapters (
    number INTEGER NOT NULL CHECK(number > 0),
    revision INTEGER NOT NULL CHECK(revision > 0),
    body BLOB NOT NULL, digest TEXT NOT NULL,
    PRIMARY KEY(number, revision), UNIQUE(number, digest)
);
CREATE TABLE adopted (
    number INTEGER PRIMARY KEY, revision INTEGER NOT NULL,
    FOREIGN KEY(number, revision) REFERENCES chapters
);
CREATE TABLE notes (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, detail TEXT NOT NULL,
    number INTEGER, revision INTEGER, quote TEXT, closed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(number, revision) REFERENCES chapters
);
CREATE TABLE packets (
    id TEXT PRIMARY KEY, number INTEGER NOT NULL, revision INTEGER NOT NULL,
    reader TEXT NOT NULL REFERENCES readers(name), handle TEXT NOT NULL,
    UNIQUE(number,revision,reader,handle), FOREIGN KEY(number, revision) REFERENCES chapters
);
CREATE TABLE feedback (
    number INTEGER NOT NULL, revision INTEGER NOT NULL, reader TEXT NOT NULL REFERENCES readers(name),
    origin TEXT NOT NULL, packet_id TEXT REFERENCES packets(id), response BLOB NOT NULL, PRIMARY KEY(number, revision, reader),
    FOREIGN KEY(number, revision) REFERENCES chapters
);
PRAGMA application_id = 0x5741424b;
PRAGMA user_version = 1;
"""


def upgrade(db, target=SCHEMA_VERSION):
    from .features import SCHEMAS
    from .story import chapter_cards

    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == target:
        return
    if version == 2:
        bookmark_columns = {r[1] for r in db.execute("PRAGMA table_info(creative_bookmarks)")}
        if bookmark_columns and "baseline" not in bookmark_columns:
            db.execute("ALTER TABLE creative_bookmarks ADD COLUMN baseline TEXT")
    earlier_schemas = SCHEMAS if version < 3 else ()
    for script in earlier_schemas:
        if version == 2:
            script = re.sub(r"CREATE (TABLE|(?:UNIQUE )?INDEX) (?!IF NOT EXISTS )",
                            r"CREATE \1 IF NOT EXISTS ", script)
        current = ""
        for part in script.split(";"):
            current += part + ";"
            if current.strip() != ";" and sqlite3.complete_statement(current):
                db.execute(current)
                current = ""
    if target >= 4:
        db.execute(chapter_cards.SCHEMA)
    db.execute(f"PRAGMA user_version = {target}")


@contextmanager
def new_book(directory, title, first=1, source_case=None):
    if not title.strip():
        raise ValueError("Book title is empty.")
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / "book.sqlite3"
    if dest.exists():
        raise ValueError("A book already exists in this directory.")
    with tempfile.NamedTemporaryFile(dir=directory) as staging:
        connection = sqlite3.connect(staging.name)
        try:
            connection.executescript(SCHEMA)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                connection.execute("INSERT INTO book VALUES (?,?,?)", (title, first, source_case))
                upgrade(connection)
                yield connection
        finally:
            connection.close()
        os.link(staging.name, dest)


def connect(directory, writable=False):
    path = (directory / "book.sqlite3").resolve()
    if not path.is_file():
        raise ValueError("Book not found. Select the book directory or use init.")
    mode = "rw" if writable else "ro"
    db = sqlite3.connect(path.as_uri() + "?mode=" + mode, uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        if (db.execute("PRAGMA application_id").fetchone()[0] != 0x5741424B or
                db.execute("PRAGMA user_version").fetchone()[0] not in (1, 2, 3, SCHEMA_VERSION)):
            raise ValueError("Unsupported book format.")
        db.execute("PRAGMA trusted_schema = OFF")
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("BEGIN IMMEDIATE" if writable else "BEGIN")
        if writable:
            upgrade(db)
    except BaseException:
        db.close()
        raise
    return db


def text_bytes(raw):
    if not raw.decode("utf-8").strip():
        raise ValueError("Text is empty.")
    return raw


def chapter(db, number, revision=None):
    row = db.execute("""
        SELECT c.*, (a.revision IS c.revision) AS adopted FROM chapters c
        LEFT JOIN adopted a ON c.number=a.number
        WHERE c.number=? AND (? IS NULL OR c.revision=?)
        ORDER BY adopted DESC, c.revision DESC LIMIT 1
    """, (number, revision, revision)).fetchone()
    if row is None:
        raise ValueError("Chapter or revision not found.")
    return row


def save(db, number, raw):
    raw = text_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.execute("SELECT revision FROM chapters WHERE number=? AND digest=?", (number, digest)).fetchone()
    if existing:
        return dict(number=number, revision=existing[0], sha256=digest)
    first = db.execute("SELECT first_chapter FROM book").fetchone()[0]
    if number < first:
        raise ValueError("Chapter precedes the start of this book or excerpt.")
    if number > first:
        chapter(db, number - 1)
    rev = db.execute("SELECT coalesce(max(revision), 0) + 1 FROM chapters WHERE number=?", (number,)).fetchone()[0]
    db.execute("INSERT INTO chapters VALUES (?, ?, ?, ?)", (number, rev, raw, digest))
    return dict(number=number, revision=rev, sha256=digest)


def add_note(db, kind, detail, number, revision, quote):
    if not detail.strip():
        raise ValueError("Note is empty.")
    has_source = (number is not None, revision is not None, quote is not None)
    if any(has_source) and not all(has_source):
        raise ValueError("Provide the chapter, revision and exact quote together.")
    if kind == "fact" and not all(has_source):
        raise ValueError("A confirmed fact needs a source in the manuscript.")
    if all(has_source):
        body = chapter(db, number, revision)["body"].decode("utf-8")
        if not quote.strip() or quote not in body:
            raise ValueError("Quote does not appear in this chapter revision.")
    row = db.execute("INSERT INTO notes(kind,detail,number,revision,quote) VALUES(?,?,?,?,?)",
                     (kind, detail, number, revision, quote))
    return {"id": row.lastrowid}


def current_card_version(db, number, revision):
    if db.execute("PRAGMA user_version").fetchone()[0] >= 4:
        return db.execute("SELECT max(version) FROM chapter_cards WHERE number=? AND revision=?",
                          (number, revision)).fetchone()[0]
    return None


def handoff(db, target):
    info = dict(db.execute("SELECT * FROM book").fetchone())
    if target < info["first_chapter"]:
        raise ValueError("Chapter precedes the available excerpt.")
    result = {**info, "next_chapter": target,
              "previous_chapter": None, "notes": [], "notes_for_review": []}
    if target > info["first_chapter"]:
        row = chapter(db, target - 1)
        result["previous_chapter"] = dict(number=row["number"], revision=row["revision"],
                                           status="adopted" if row["adopted"] else "draft", body=row["body"].decode("utf-8"))
        result["previous_chapter"]["card_version"] = current_card_version(db, row["number"], row["revision"])
    rows = db.execute("""
        SELECT n.id, n.kind, n.detail, n.number, n.revision, n.quote,
               n.revision = coalesce(a.revision, (SELECT max(c.revision) FROM chapters c
                                                  WHERE c.number=n.number)) AS source_is_current
          FROM notes n LEFT JOIN adopted a ON a.number=n.number
         WHERE n.closed=0 AND (n.number IS NULL OR n.number < ?) ORDER BY n.id
    """, (target,))
    for row in rows:
        item = dict(row)
        if item["number"] is not None:
            item["source_is_current"] = bool(item["source_is_current"])
        if item["kind"] == "fact":
            item["annotation"] = item.pop("detail")
        if item.get("source_is_current") is False:
            result["notes_for_review"].append(item)
        else:
            result["notes"].append(item)
    return result


def recall(db, before, terms):
    words = [word.casefold() for query in terms for word in query.split()]
    if not words:
        raise ValueError("Enter a search term.")
    matches = []
    for (number,) in db.execute("SELECT DISTINCT number FROM chapters WHERE number < ? ORDER BY number", (before,)):
        row = chapter(db, number)
        lines = row["body"].decode("utf-8").splitlines(keepends=True)
        positions = [i for i, line in enumerate(lines) if line.strip()]
        paragraphs = [lines[i] for i in positions]
        spans = []
        for index, para in enumerate(paragraphs):
            if all(word in para.casefold() for word in words):
                start, end = max(index - 1, 0), min(index + 2, len(paragraphs))
                if spans and start <= spans[-1][1]:
                    spans[-1] = (spans[-1][0], end)
                else:
                    spans.append((start, end))
        for start, end in spans:
            matches.append(dict(number=number, revision=row["revision"], first_paragraph=start + 1,
                                last_paragraph=end, status="adopted" if row["adopted"] else "draft",
                                excerpt="".join(lines[positions[start]:positions[end-1]+1])))
    return matches


def packet(db, number, revision, reader):
    row = chapter(db, number, revision)
    recorded = db.execute("SELECT origin FROM feedback WHERE number=? AND revision=? AND reader=?",
                          (number, revision, reader)).fetchone()
    if recorded and recorded["origin"] == "historical":
        raise ValueError("For a fresh reading, import the case into a new book with --manuscript-only.")
    session = db.execute("SELECT handle FROM readers WHERE name=?", (reader,)).fetchone()
    if session is None or not session[0]:
        raise ValueError("Register the reader's actual session handle first.")
    handle = session[0]
    key = (number, revision, reader, handle)
    issued = db.execute("SELECT id FROM packets WHERE number=? AND revision=? AND reader=? AND handle=?", key).fetchone()
    packet_id = issued[0] if issued else uuid.uuid4().hex
    if issued is None:
        db.execute("INSERT INTO packets VALUES(?,?,?,?,?)", (packet_id, *key))
    return dict(packet=packet_id, reader=reader, handle=handle, number=number, revision=revision,
                sha256=row["digest"], text=row["body"].decode("utf-8"))


def add_response(db, number, revision, reader, raw, origin, packet_id=None):
    raw = text_bytes(raw)
    identity = (number, revision, reader)
    old = db.execute("SELECT response,packet_id FROM feedback WHERE number=? AND revision=? AND reader=?", identity).fetchone()
    if old:
        if old[0] != raw or old[1] != packet_id:
            raise ValueError("This reader already recorded feedback on this revision.")
    else:
        db.execute("INSERT INTO feedback VALUES(?,?,?,?,?,?)", (*identity, origin, packet_id, raw))
    return dict(number=number, revision=revision, reader=reader)


def feedback(db, packet_id, digest, raw):
    row = db.execute("SELECT * FROM packets WHERE id=?", (packet_id,)).fetchone()
    if row is None:
        raise ValueError("Reader packet not found in this book.")
    if digest != chapter(db, row["number"], row["revision"])["digest"]:
        raise ValueError("Reader packet digest differs from the chapter.")
    return add_response(db, row["number"], row["revision"], row["reader"], raw, "reader-session", packet_id)
