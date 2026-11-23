"""Consistent private book snapshots with verified, no-overwrite restoration."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

from .. import book


def register(subs):
    p = subs.add_parser("backup", help="save a consistent whole-book SQLite snapshot")
    p.add_argument("destination", type=Path)
    p = subs.add_parser("restore", help="restore a verified snapshot into an unused book directory")
    p.add_argument("snapshot", type=Path)
    p.add_argument("--sha256", required=True)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_idle(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='world_adapter_attempts'").fetchone():
        if db.execute("SELECT 1 FROM world_adapter_attempts WHERE stage='dispatching' LIMIT 1").fetchone():
            raise ValueError("Recover the outstanding world decision before taking a snapshot.")
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wa_tasks'").fetchone():
        if db.execute("SELECT 1 FROM wa_tasks WHERE state='running' LIMIT 1").fetchone():
            raise ValueError("A task has an outstanding attempt. Complete or recover it before taking a snapshot.")


def check_structure(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    with closing(sqlite3.connect(":memory:")) as expected:
        expected.executescript(book.SCHEMA)
        if version == 2:
            raise ValueError("Upgrade this pre-release book before taking or restoring a snapshot.")
        if version >= 3:
            book.upgrade(expected, version)
        tables = expected.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for (name,) in tables:
            # All identifiers come from the trusted in-memory schema.
            query = f'PRAGMA table_info("{name}")'
            if list(map(tuple, db.execute(query))) != list(expected.execute(query)):
                raise ValueError("Snapshot has an incomplete or incompatible book schema.")
    if db.execute("SELECT count(*) FROM book").fetchone()[0] != 1:
        raise ValueError("Snapshot must contain exactly one book.")
    if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger', 'view')").fetchone():
        raise ValueError("Snapshot contains unsupported active database objects.")


def execute(args):
    restoring = args.command == "restore"
    dest = args.book / "book.sqlite3" if restoring else args.destination
    if dest.exists():
        raise ValueError("Destination already exists.")
    dest.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as work:
        snapshot = Path(work) / "book.sqlite3"
        if restoring:
            shutil.copyfile(args.snapshot, snapshot)
            if digest(snapshot) != args.sha256:
                raise ValueError("Snapshot digest mismatch.")
        else:
            with closing(book.connect(args.book)) as source, closing(sqlite3.connect(snapshot)) as target:
                check_idle(source)
                source.backup(target)
        os.chmod(snapshot, 0o600)
        with closing(book.connect(Path(work))) as check:
            check_structure(check)
            check_idle(check)
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or check.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Snapshot integrity check failed.")
        checksum = digest(snapshot)
        os.link(snapshot, dest)
    return {"path": str(dest), "sha256": checksum}
