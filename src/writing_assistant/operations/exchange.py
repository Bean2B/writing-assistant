"""Manual local exchange. A received response remains in quarantine until accepted."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import uuid

from .. import book

COMMANDS = {"exchange", "diagnostics"}
SCHEMA = """
CREATE TABLE exchanges (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL,
    packet TEXT REFERENCES packets(id), response_name TEXT NOT NULL, stage TEXT NOT NULL,
    received TEXT, return_digest TEXT
);
"""
MAX_SIZE = 4 * 1024 * 1024


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def register(subs):
    sub = subs.add_parser("exchange", help="prepare local outgoing material and quarantine returns").add_subparsers(
        dest="operation", required=True)
    p = sub.add_parser("reader")
    p.add_argument("--packet", required=True)
    p = sub.add_parser("source-window")
    p.add_argument("--window", required=True)
    p.add_argument("--actor", required=True)
    p = sub.add_parser("engineering")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--input", action="append", required=True)
    p.add_argument("--response-name", required=True)
    for name in ("show", "receive", "accept", "result"):
        p = sub.add_parser(name)
        p.add_argument("id")
        if name == "receive":
            p.add_argument("--file", type=Path, required=True)
        if name == "accept":
            p.add_argument("--return-sha256", required=True)
    subs.add_parser("diagnostics", help="show integrity and workflow counts without manuscript or credentials")


def writable(args):
    return args.command == "exchange" and args.operation not in {"show", "result"}


def outgoing(db, kind, materials, name, packet=None):
    if not re.fullmatch(r"[\w.-]{1,96}", name) or name in {".", ".."}:
        raise ValueError("Response name must be a single logical filename.")
    key = uuid.uuid4().hex
    body = {"format": "writing-assistant/exchange/1", "id": key, "kind": kind,
            "materials": materials, "response_name": name}
    raw = canonical(body)
    if len(raw.encode()) > MAX_SIZE:
        raise ValueError("Exchange exceeds the supported package size.")
    digest = sha(raw.encode())
    db.execute("INSERT INTO exchanges VALUES(?,?,?,?,?,?,'ready-unsent',NULL,NULL)",
               (key, kind, raw, digest, packet, name))
    return {"request": body, "request_sha256": digest, "stage": "ready-unsent"}


def git_files(args):
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.commit):
        raise ValueError("Supply the full Git commit id.")
    cmd = ["git", "--no-replace-objects", "-C", str(args.repo)]
    def git(*argv):
        result = subprocess.run([*cmd, *argv], capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError("The requested commit or tracked input is unavailable.")
        return result.stdout
    if git("cat-file", "-t", args.commit).strip() != b"commit":
        raise ValueError("Expected a Git commit.")
    files = []
    total = 0
    for name in dict.fromkeys(args.input):
        path = PurePosixPath(name)
        if path.is_absolute() or str(path) != name or ".." in path.parts or not path.parts:
            raise ValueError("Input must be an exact relative path.")
        listing = git("ls-tree", "-z", args.commit, "--", ":(literal)" + name)
        mode, sep, found = listing.partition(b"\t")
        if not sep or found != name.encode() + b"\0" or mode.split()[0] not in {b"100644", b"100755"}:
            raise ValueError("Input must identify one tracked regular file.")
        blob = mode.split()[2].decode()
        total += int(git("cat-file", "-s", blob))
        if total > MAX_SIZE:
            raise ValueError("Selected inputs exceed the package size.")
        raw = git("cat-file", "blob", blob)
        files.append({"path": name, "commit": args.commit, "sha256": sha(raw), "text": raw.decode()})
    return files


def run(db, args):
    if args.command == "diagnostics":
        # Fixed field names keep editorial text, filesystem paths and host tokens out of this projection.
        return {"integrity": "ok" if db.execute("PRAGMA quick_check").fetchone()[0] == "ok" else "failed",
                "schema": db.execute("PRAGMA user_version").fetchone()[0],
                "foreign_key_issues": sum(1 for _ in db.execute("PRAGMA foreign_key_check")),
                "draft_revisions": db.execute("SELECT count(*) FROM chapters").fetchone()[0],
                "exchange_counts": dict(db.execute("SELECT stage,count(*) FROM exchanges GROUP BY stage"))}
    action = args.operation
    if action == "reader":
        p = db.execute("SELECT * FROM packets WHERE id=?", (args.packet,)).fetchone()
        if not p:
            raise ValueError("Unknown reader packet.")
        row = book.chapter(db, p["number"], p["revision"])
        return outgoing(db, "reader", [{"text": row["body"].decode(), "sha256": row["digest"]}],
                        "feedback.md", args.packet)
    if action == "source-window":
        row = db.execute("""SELECT w.lo,w.hi,w.digest,s.lo AS base,s.source_span,s.source_digest
                            FROM study_windows w JOIN study_sources s ON s.id=w.study
                            WHERE w.id=? AND w.actor=?""", (args.window, args.actor)).fetchone()
        if not row:
            raise ValueError("No study window bound to this actor.")
        text = row["source_span"][row["lo"]-row["base"]:row["hi"]-row["base"]]
        if sha(text.encode()) != row["digest"]:
            raise ValueError("Source window identity mismatch.")
        return outgoing(db, "study", [{"text": text, "sha256": row["digest"],
                        "source_sha256": row["source_digest"], "range": [row["lo"], row["hi"]]}], "analysis.md")
    if action == "engineering":
        return outgoing(db, "engineering", git_files(args), args.response_name)
    row = db.execute("SELECT * FROM exchanges WHERE id=?", (args.id,)).fetchone()
    if not row:
        raise ValueError("Unknown exchange.")
    if action == "show":
        return {"request": json.loads(row["body"]), "stage": row["stage"], "request_sha256": row["digest"]}
    if action == "receive":
        with args.file.open("rb") as stream:
            raw = stream.read(MAX_SIZE + 1)
        if len(raw) > MAX_SIZE:
            raise ValueError("Response exceeds the package size.")
        obj = json.loads(raw)
        expected = {"format", "id", "request_sha256", "name", "text", "sha256"}
        if (not isinstance(obj, dict) or set(obj) != expected or obj["format"] != "writing-assistant/return/1"
                or obj["id"] != row["id"] or obj["request_sha256"] != row["digest"]
                or obj["name"] != row["response_name"] or not isinstance(obj["text"], str)
                or not obj["text"].strip() or sha(obj["text"].encode()) != obj["sha256"]):
            raise ValueError("Unbound or invalid response.")
        digest = sha(canonical(obj).encode())
        if row["return_digest"] and row["return_digest"] != digest:
            raise ValueError("An earlier return is already preserved.")
        if not row["return_digest"]:
            db.execute("UPDATE exchanges SET received=?,return_digest=?,stage='quarantined' WHERE id=?",
                       (obj["text"], digest, row["id"]))
        return {"id": row["id"], "return_sha256": digest,
                "stage": row["stage"] if row["return_digest"] else "quarantined"}
    if not row["return_digest"]:
        raise ValueError("No response has been received.")
    if action == "result":
        return {"stage": row["stage"], "text": row["received"], "return_sha256": row["return_digest"]}
    if args.return_sha256 != row["return_digest"]:
        raise ValueError("Return digest mismatch.")
    if row["stage"] != "accepted":
        if row["kind"] == "reader":
            digest = json.loads(row["body"])["materials"][0]["sha256"]
            book.feedback(db, row["packet"], digest, row["received"].encode())
        db.execute("UPDATE exchanges SET stage='accepted' WHERE id=?", (row["id"],))
    return {"id": row["id"], "stage": "accepted", "return_sha256": row["return_digest"]}
