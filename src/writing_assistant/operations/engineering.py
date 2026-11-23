"""Local candidate inspection and coordinator-bound Git admission."""
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
import sys
import tempfile

from ..filesystem import exclusive_file, file_identity


COMMANDS = {"engineering"}
ADMISSION = "refs/writing-assistant/admissions/current"


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(repo, *args, data=None, missing=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="Writing Assistant", GIT_AUTHOR_EMAIL="local@invalid",
               GIT_COMMITTER_NAME="Writing Assistant", GIT_COMMITTER_EMAIL="local@invalid")
    try:
        proc = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, "-C", str(repo), *args],
                              env=env, input=data, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git operation timed out: " + args[0]) from exc
    if proc.returncode:
        if missing and proc.returncode == 1:
            return None
        raise ValueError("Git operation failed: " + args[0])
    return proc.stdout


def oid(repo, name):
    # --verify on a specified full ref distinguishes a missing admission ref.
    raw = git(repo, "show-ref", "--verify", "--hash", name) if name != ADMISSION else None
    if name == ADMISSION:
        exists = git(repo, "show-ref", "--verify", "--quiet", name, missing=True)
        if exists is None:
            return None
        raw = git(repo, "show-ref", "--verify", "--hash", name)
    return raw.decode("ascii").strip()


def common_dir(repo):
    root = Path(repo).resolve(strict=True)
    common = Path(os.fsdecode(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").rstrip(b"\r\n")))
    if not common.is_dir():
        raise ValueError("Git repository unavailable.")
    return root, common.resolve(strict=True)


def check_commit(repo, value):
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise ValueError("Require a full Git commit OID.")
    if git(repo, "cat-file", "-t", value).strip() != b"commit":
        raise ValueError("Expected a Git commit.")


def check_branch(repo, ref):
    if not ref.startswith("refs/heads/") or ref == "refs/heads/main":
        raise ValueError("Supply a specific candidate branch ref.")
    git(repo, "check-ref-format", ref)


def scope(repo, base, candidate):
    if base == candidate or git(repo, "merge-base", "--is-ancestor", base, candidate, missing=True) is None:
        raise ValueError("Candidate must fast-forward the pinned base.")
    raw = git(repo, "diff", "--name-only", "--no-renames", "--no-ext-diff", "-z", base, candidate, "--")
    paths = sorted(os.fsdecode(path) for path in raw.split(b"\0") if path)
    if not paths:
        raise ValueError("Candidate has no file changes.")
    return paths


def check_worktrees(repo):
    listing = git(repo, "worktree", "list", "--porcelain", "-z")
    if b"branch refs/heads/main" in listing.split(b"\0"):
        raise ValueError("The main branch is checked out in a worktree.")


class Coordinator:
    """Caller owns the registry directory, authorizations and review event lookups."""

    def __init__(self, registry, repo):
        self.repo, common = common_dir(repo)
        self.identity = str(common)
        self.common = common
        self.store = Path(registry).resolve()
        if self.store == self.repo or self.repo in self.store.parents or common in self.store.parents:
            raise ValueError("Keep the coordinator's database outside the candidate repository.")

    @contextlib.contextmanager
    def database(self, initialize=False):
        if initialize:
            self.store.mkdir(mode=0o700, parents=True, exist_ok=True)
        file = self.store / "engineering.sqlite3"
        if not initialize and not file.is_file():
            raise ValueError("Engineering repository is not enrolled.")
        with exclusive_file(self.store / "engineering.lock"):
            db = sqlite3.connect(file)
            db.row_factory = sqlite3.Row
            try:
                if initialize:
                    db.executescript("""
                        CREATE TABLE IF NOT EXISTS repos(repo TEXT PRIMARY KEY, device INTEGER, inode INTEGER,
                          accepted TEXT, highwater TEXT);
                        CREATE TABLE IF NOT EXISTS candidates(repo TEXT, task TEXT, base TEXT, head TEXT,
                          ref TEXT, author TEXT, paths TEXT, state TEXT, verification TEXT, evidence TEXT,
                          old_admission TEXT, new_admission TEXT, PRIMARY KEY(repo,task));
                        CREATE TABLE IF NOT EXISTS reviews(repo TEXT, task TEXT, reviewer TEXT, event TEXT,
                          verdict TEXT, detail TEXT, PRIMARY KEY(repo,task,reviewer), UNIQUE(repo,event));
                        CREATE TABLE IF NOT EXISTS attempts(repo TEXT, task TEXT, number INTEGER,
                          result TEXT, PRIMARY KEY(repo,task,number));
                    """)
                with db:
                    yield db
            finally:
                db.close()

    def enroll(self):
        """Trusted coordinator explicitly enrolls the current physical repository."""
        with self.database(True) as db:
            main, admission = oid(self.repo, "refs/heads/main"), oid(self.repo, ADMISSION)
            entry = db.execute("SELECT * FROM repos WHERE repo=?", (self.identity,)).fetchone()
            if entry:
                self._entry(db)
                if (entry["accepted"], entry["highwater"]) != (main, admission):
                    raise ValueError("Registered references drifted.")
            elif admission:
                raise ValueError("Found an admission ref without its trusted registry.")
            else:
                db.execute("INSERT INTO repos VALUES(?,?,?,?,NULL)", (self.identity, *file_identity(self.common), main))
        return {"base": main, "admission": admission}

    def _entry(self, db):
        row = db.execute("SELECT * FROM repos WHERE repo=?", (self.identity,)).fetchone()
        if not row:
            raise ValueError("Engineering repository is not enrolled.")
        if file_identity(self.common) != (row["device"], row["inode"]):
            raise ValueError("Enrolled Git directory identity changed.")
        return row

    def _candidate(self, db, task):
        self._entry(db)
        row = db.execute("SELECT * FROM candidates WHERE repo=? AND task=?", (self.identity, task)).fetchone()
        if row is None:
            raise ValueError("Candidate unavailable.")
        return row

    def _match(self, db, row):
        entry = self._entry(db)
        if (oid(self.repo, "refs/heads/main") != row["base"] or entry["accepted"] != row["base"]
                or oid(self.repo, ADMISSION) != entry["highwater"] or oid(self.repo, row["ref"]) != row["head"]):
            raise ValueError("Candidate, main or admission reference changed.")
        if scope(self.repo, row["base"], row["head"]) != json.loads(row["paths"]):
            raise ValueError("Changed paths differ from the reviewed scope.")
        other = db.execute("SELECT task FROM candidates WHERE repo=? AND state='intent' LIMIT 1",
                           (self.identity,)).fetchone()
        if other:
            raise ValueError("An unresolved admission intent requires reconciliation.")

    @staticmethod
    def binding(row):
        return {"repo": row["repo"], "task": row["task"], "base": row["base"], "candidate": row["head"],
                "ref": row["ref"], "paths": json.loads(row["paths"])}

    def propose(self, task, base, candidate, ref, author, paths):
        if not task.strip() or not author.strip() or author != author.strip():
            raise ValueError("Task and author must be named.")
        check_branch(self.repo, ref)
        for value in (base, candidate):
            check_commit(self.repo, value)
        if sorted(paths) != scope(self.repo, base, candidate):
            raise ValueError("Supply the exact changed file paths.")
        with self.database() as db:
            db.execute("""INSERT INTO candidates(repo,task,base,head,ref,author,paths,state)
                          VALUES(?,?,?,?,?,?,?,'proposed')""",
                       (self.identity, task, base, candidate, ref, author, json.dumps(sorted(paths))))
            row = self._candidate(db, task)
            self._match(db, row)
            return self.binding(row)

    def verify(self, task):
        with self.database() as db:
            row = self._candidate(db, task)
            self._match(db, row)
            if row["state"] != "proposed":
                raise ValueError("The candidate is closed.")
            report = smoke_fixture(self.repo, row["head"], self.store)
            number = db.execute("SELECT count(*) FROM attempts WHERE repo=? AND task=?",
                                (self.identity, task)).fetchone()[0] + 1
            db.execute("INSERT INTO attempts VALUES(?,?,?,?)", (self.identity, task, number, json.dumps(report)))
            db.execute("UPDATE candidates SET verification=? WHERE repo=? AND task=?",
                       (json.dumps(report), self.identity, task))
            return report

    def record_review(self, task, event_id, lookup):
        """Lookup supplies the authenticated host event for this immutable review."""
        event = lookup(event_id)
        with self.database() as db:
            row = self._candidate(db, task)
            self._match(db, row)
            binding = self.binding(row)
            if (not isinstance(event, dict) or event.get("id") != event_id or not event_id
                    or event.get("operation") != "engineering-review" or event.get("binding") != binding
                    or row["state"] != "proposed"):
                raise ValueError("Review does not bind the open candidate.")
            reviewer, verdict, detail = event.get("reviewer"), event.get("verdict"), event.get("review")
            if (not isinstance(reviewer, str) or not reviewer.strip() or reviewer != reviewer.strip() or reviewer == row["author"]
                    or verdict not in ("accept", "reject") or not isinstance(detail, str) or not detail.strip()):
                raise ValueError("Expected an independent review, verdict and original response.")
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)", (self.identity, task, reviewer, event_id,
                                                                   verdict, detail))
        return {"reviewer": reviewer, "verdict": verdict, "id": event_id}

    def _receipt(self, db, row, auth):
        binding = self.binding(row)
        if (not isinstance(auth, dict) or auth.get("binding") != binding or auth.get("operation") != "admit-local-main"
                or not isinstance(auth.get("authors"), list) or row["author"] not in auth["authors"]):
            raise ValueError("User decision does not bind this local admission and its authors.")
        verification = json.loads(row["verification"] or "null")
        if not verification or verification["status"] != "passed" or verification["candidate"] != row["head"]:
            raise ValueError("A passing check on the fixed candidate is required.")
        reviews = [dict(r) for r in db.execute("""SELECT reviewer,event,verdict,detail FROM reviews
                                                  WHERE repo=? AND task=? ORDER BY reviewer""",
                                               (self.identity, row["task"]))]
        if len(reviews) < 2 or any(r["reviewer"] in auth["authors"] or r["verdict"] != "accept" for r in reviews):
            raise ValueError("Two distinct favorable nonauthor reviews are required.")
        return {"format": "writing-assistant/admission/1", "binding": binding, "user_event": auth["id"],
                "reviews": [{"id": r["event"], "sha256": digest(r["detail"].encode())} for r in reviews],
                "verification": verification}

    def admit(self, task, event_id, lookup):
        auth = lookup(event_id)
        if not event_id or not isinstance(auth, dict) or auth.get("id") != event_id:
            raise ValueError("A trusted coordinator must resolve the current user decision.")
        with self.database() as db:
            row = self._candidate(db, task)
            self._match(db, row)
            if row["state"] != "proposed":
                raise ValueError("The candidate is closed.")
            check_worktrees(self.repo)
            receipt = self._receipt(db, row, auth)
            old = self._entry(db)["highwater"]
            tree = git(self.repo, "rev-parse", row["head"] + "^{tree}").decode().strip()
            new = git(self.repo, "commit-tree", tree, *(["-p", old] if old else []),
                      "-F", "-", data=packed(receipt)).decode().strip()
            old_or_zero = old or "0" * len(new)
            db.execute("UPDATE candidates SET state='intent',old_admission=?,new_admission=?,evidence=? WHERE repo=? AND task=?",
                       (old, new, json.dumps(receipt), self.identity, task))
            db.commit()
            transaction = (f"start\nverify {row['ref']} {row['head']}\n"
                           f"update refs/heads/main {row['head']} {row['base']}\n"
                           f"update {ADMISSION} {new} {old_or_zero}\nprepare\ncommit\n")
            git(self.repo, "update-ref", "--stdin", data=transaction.encode("utf-8"))
            return self._recover(db, self._candidate(db, task))

    def _recover(self, db, row):
        if row["state"] != "intent":
            raise ValueError("No outstanding admission intent.")
        current = (oid(self.repo, "refs/heads/main"), oid(self.repo, ADMISSION))
        if current != (row["head"], row["new_admission"]):
            raise ValueError("Admission outcome is uncertain. Preserve the original intent.")
        changed = db.execute("UPDATE repos SET accepted=?,highwater=? WHERE repo=? AND accepted=? AND highwater IS ?",
                             (*current, self.identity, row["base"], row["old_admission"])).rowcount
        if changed != 1:
            raise ValueError("Registry no longer matches the prepared admission.")
        db.execute("UPDATE candidates SET state='admitted' WHERE repo=? AND task=?", (self.identity, row["task"]))
        return {"state": "admitted", "main": current[0], "admission": current[1]}

    def recover(self, task):
        with self.database() as db:
            return self._recover(db, self._candidate(db, task))

    def status(self, task):
        with self.database() as db:
            row = self._candidate(db, task)
            return {**self.binding(row), "state": row["state"],
                    "verification": json.loads(row["verification"] or "null"),
                    "attempts": [json.loads(r[0]) for r in db.execute(
                        "SELECT result FROM attempts WHERE repo=? AND task=? ORDER BY number", (self.identity, task))],
                    "reviews": [dict(r) for r in db.execute(
                        "SELECT reviewer,event,verdict FROM reviews WHERE repo=? AND task=?", (self.identity, task))]}


def fixture_python():
    framework = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    return framework.resolve() if framework.is_file() else Path(sys.executable).resolve()


def fixture_profile(source, scratch, protected):
    def subpath(path):
        return "(subpath " + json.dumps(str(Path(path).resolve())) + ")"
    # System libraries need general read access to platform resources. Exclude
    # home directories, temporary areas, mounted volumes and both owner stores.
    excluded = ["/Users", Path.home(), "/private/var/folders", "/private/tmp", "/Volumes", *protected]
    runtime = Path(sys.base_prefix).resolve()
    executable = fixture_python()
    return " ".join([
        "(version 1)", "(deny default)", "(allow file-read*)",
        "(deny file-read* " + " ".join(subpath(p) for p in excluded) + ")",
        "(allow file-read* " + " ".join(subpath(p) for p in [source, scratch, runtime]) + ")",
        "(allow file-read-metadata " + " ".join('(literal ' + json.dumps(str(p)) + ')' for p in scratch.parents) + ")",
        "(allow file-write* " + subpath(scratch) + ' (literal "/dev/null"))',
        "(allow sysctl-read)", "(allow process-exec (literal " + json.dumps(str(executable)) + "))",
    ])


def smoke_fixture(repo, candidate, registry):
    """Run the fixed candidate's launcher against a disposable synthetic book."""
    report = {"fixture": "book-roundtrip/1", "candidate": candidate, "status": "failed", "steps": []}
    sandbox = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not sandbox.is_file():
        report["steps"].append({"result": "macos-sandbox-unavailable"})
        return report
    paths = ["scripts/writing-assistant", "src/writing_assistant"]
    entries = git(repo, "ls-tree", "-r", "-z", candidate, "--", *paths).split(b"\0")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        scratch = root / "work"
        scratch.mkdir()
        source = root / "candidate"
        for entry in filter(None, entries):
            header, name = entry.split(b"\t", 1)
            mode, kind, ref = header.split()
            relative = PurePosixPath(os.fsdecode(name))
            if mode not in (b"100644", b"100755") or kind != b"blob" or ".." in relative.parts or relative.is_absolute():
                raise ValueError("The fixture expects regular source files in the candidate tree.")
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(git(repo, "cat-file", "blob", ref.decode("ascii")))
        sample = "渡船靠在北岸。\r\n".encode()
        env = {"PATH": os.defpath, "HOME": str(scratch), "TMPDIR": str(scratch), "PYTHONIOENCODING": "utf-8"}
        profile = fixture_profile(source, scratch, [repo, registry])
        base = [str(sandbox), "-p", profile, str(fixture_python()), "-I", "-B",
                str(source / paths[0]), "--book", str(scratch / "fixture-book")]
        for args, data in [(["init", "Fixture"], None), (["save", "1"], sample), (["read", "1", "--revision", "1"], None)]:
            try:
                p = subprocess.run(base + args, input=data, capture_output=True, env=env, cwd=scratch, timeout=15)
            except subprocess.TimeoutExpired:
                report["steps"].append({"command": args[0], "result": "timed-out"})
                return report
            passed = p.returncode == 0
            if args[0] == "save" and passed:
                try:
                    capture = json.loads(p.stdout)
                    passed = isinstance(capture, dict) and capture.get("sha256") == digest(sample)
                except (UnicodeError, ValueError):
                    passed = False
            if args[0] == "read":
                passed = passed and p.stdout == sample
            report["steps"].append({"command": args[0], "exit": p.returncode, "passed": passed,
                                    "stdout_sha256": digest(p.stdout), "stderr_sha256": digest(p.stderr)})
            if not passed:
                return report
    report["status"] = "passed"
    return report


def register(subs):
    p = subs.add_parser("engineering", help="inspect a pinned local Git candidate")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--registry", type=Path, required=True, help="already enrolled coordinator registry directory")
    s = p.add_subparsers(dest="engineering_action", required=True)
    p = s.add_parser("propose")
    for key in ("task", "base", "candidate", "ref", "author"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--path", action="append", required=True, help="one exact changed file, repeat as needed")
    for operation in ("verify", "status", "recover"):
        s.add_parser(operation).add_argument("task")


def execute(args):
    owner = Coordinator(args.registry, args.repo)
    if args.engineering_action == "propose":
        return owner.propose(args.task, args.base, args.candidate, args.ref, args.author, args.path)
    result = getattr(owner, args.engineering_action)(args.task)
    if args.engineering_action == "verify" and result["status"] != "passed":
        raise ValueError("Candidate verification failed. The original attempt is available through status.")
    return result
