"""Fixed-order, version-bound reading trials and explicit adoption decisions."""
import hashlib
import json
from pathlib import Path
import uuid

from .. import book


COMMANDS = {"trial"}
SCHEMA = """
CREATE TABLE trial_runs (
    id TEXT PRIMARY KEY, run_key TEXT NOT NULL UNIQUE, origin TEXT NOT NULL, evaluation TEXT
);
CREATE TABLE trial_plan (
    trial TEXT NOT NULL REFERENCES trial_runs(id), step INTEGER NOT NULL, arm TEXT NOT NULL, chapter INTEGER NOT NULL,
    revision INTEGER NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(trial,step),
    UNIQUE(trial,arm,chapter,revision), FOREIGN KEY(chapter,revision) REFERENCES chapters
);
CREATE TABLE trial_panel (
    trial TEXT NOT NULL REFERENCES trial_runs(id), reader TEXT NOT NULL, handle TEXT,
    PRIMARY KEY(trial,reader), UNIQUE(trial,handle)
);
CREATE TABLE trial_copies (
    trial TEXT NOT NULL, reader TEXT NOT NULL, step INTEGER NOT NULL, packet TEXT UNIQUE,
    response BLOB, stopped INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(trial,reader,step),
    FOREIGN KEY(trial,reader) REFERENCES trial_panel, FOREIGN KEY(trial,step) REFERENCES trial_plan
);
CREATE TABLE trial_decisions (
    event_id TEXT PRIMARY KEY, trial TEXT NOT NULL REFERENCES trial_runs(id), number INTEGER NOT NULL,
    revision INTEGER NOT NULL, digest TEXT NOT NULL, FOREIGN KEY(number,revision) REFERENCES chapters
);
"""


def register(subs):
    p = subs.add_parser("trial", help="plan and record independent readers in fixed manuscript order")
    group = p.add_subparsers(dest="trial_action", required=True)
    for action in ("create", "next", "respond", "progress", "results", "evaluate", "adopt"):
        p = group.add_parser(action)
        p.add_argument("trial")
        if action == "create":
            p.add_argument("--reader", action="append", required=True)
            p.add_argument("--item", action="append", required=True, metavar="[ARM/]CHAPTER:REVISION")
            p.add_argument("--historical", action="store_true", help="load archived feedback without session delivery")
        if action in {"next", "respond"}:
            p.add_argument("--reader", required=True)
        if action == "respond":
            p.add_argument("--packet", required=True)
            p.add_argument("--sha256", required=True)
            p.add_argument("--stop", action="store_true", help="reader explicitly chose to stop here")
        if action in {"respond", "evaluate"}:
            p.add_argument("--file", type=Path, required=True)
        if action == "adopt":
            p.add_argument("--user-event", type=Path, required=True, help="explicit host-authenticated decision in JSON")


def writable(args):
    return args.trial_action not in {"progress", "results"}


def _create(db, args):
    trial = args.trial
    names = [name.strip() for name in args.reader]
    if not trial.strip() or any(not n for n in names) or len(names) != len(set(names)):
        raise ValueError("Provide a trial id and distinct reader names.")
    items = []
    last = {}
    for item in args.item:
        arm, sep, chapter_ref = item.partition("/")
        if not sep:
            arm, chapter_ref = "default", arm
        parts = chapter_ref.split(":")
        if len(parts) != 2:
            raise ValueError("Expected chapter:revision.")
        ch, rev = map(int, parts)
        if not all(1 <= n <= 2**63-1 for n in (ch, rev)):
            raise ValueError("Invalid chapter or revision.")
        if not arm.strip() or (arm, ch, rev) in items or ch < last.get(arm, ch):
            raise ValueError("List distinct manuscripts in chronological chapter order within each comparison arm.")
        last[arm] = ch
        items.append((arm, ch, rev))
    origin = "historical" if args.historical else "reader-session"
    db.execute("INSERT INTO trial_runs(id,run_key,origin) VALUES(?,?,?)", (trial, uuid.uuid4().hex, origin))
    for step, (arm, ch, rev) in enumerate(items, 1):
        db.execute("INSERT INTO trial_plan VALUES(?,?,?,?,?,?)",
                   (trial, step, arm, ch, rev, book.chapter(db, ch, rev)["digest"]))
    for name in names:
        row = db.execute("SELECT handle FROM readers WHERE name=?", (name,)).fetchone()
        if not args.historical and (row is None or not row["handle"]):
            raise ValueError("Register the existing reader session before starting a fresh trial.")
        db.execute("INSERT INTO trial_panel VALUES(?,?,?)", (trial, name, None if args.historical else row["handle"]))
        if args.historical:
            for step, (_, ch, rev) in enumerate(items, 1):
                old = db.execute("""SELECT response FROM feedback WHERE number=? AND revision=? AND reader=?
                                    AND origin='historical'""", (ch, rev, name)).fetchone()
                if old is None:
                    raise ValueError("A requested archived response is unavailable.")
                db.execute("INSERT INTO trial_copies(trial,reader,step,response) VALUES(?,?,?,?)",
                           (trial, name, step, old["response"]))
    return _progress(db, trial)


def _run(db, trial):
    row = db.execute("SELECT * FROM trial_runs WHERE id=?", (trial,)).fetchone()
    if row is None:
        raise ValueError("Trial not found.")
    return row


def _progress(db, trial):
    trial_row = _run(db, trial)
    origin = trial_row["origin"]
    count = db.execute("SELECT count(*) FROM trial_plan WHERE trial=?", (trial,)).fetchone()[0]
    people = db.execute("""SELECT p.reader,count(c.response) AS replies,max(CASE WHEN c.stopped=1 THEN c.step END) AS stopped_at
                           FROM trial_panel p LEFT JOIN trial_copies c ON c.reader=p.reader AND c.trial=p.trial
                           WHERE p.trial=? GROUP BY p.reader ORDER BY p.reader""", (trial,))
    results = []
    for row in people:
        item = dict(row)
        if origin == "historical":
            state = "archived"
        elif row["stopped_at"] is not None:
            state = "stopped"
        elif row["replies"] == count:
            state = "completed"
        else:
            state = "reading"
        results.append({**item, "state": state})
    return {"trial": trial, "run_key": trial_row["run_key"], "origin": origin, "plan_items": count,
            "readers": results, "closed": all(item["state"] != "reading" for item in results)}


def _next(db, args):
    trial, reader = args.trial, args.reader.strip()
    if _run(db, trial)["origin"] != "reader-session":
        raise ValueError("An archived trial cannot issue live reader copies.")
    panel = db.execute("SELECT handle FROM trial_panel WHERE trial=? AND reader=?", (trial, reader)).fetchone()
    if panel is None:
        raise ValueError("Reader is outside this trial.")
    if db.execute("SELECT 1 FROM trial_copies WHERE trial=? AND reader=? AND stopped=1", (trial, reader)).fetchone():
        raise ValueError("This reader chose to stop.")
    row = db.execute("""SELECT p.*,c.packet FROM trial_plan p LEFT JOIN trial_copies c
                        ON p.trial=c.trial AND p.step=c.step AND c.reader=?
                        WHERE p.trial=? AND c.response IS NULL ORDER BY p.step LIMIT 1""", (reader, trial)).fetchone()
    if row is None:
        raise ValueError("This reader finished the plan.")
    packet = row["packet"]
    if packet is None:
        packet = uuid.uuid4().hex
        db.execute("INSERT INTO trial_copies(trial,reader,step,packet) VALUES(?,?,?,?)", (trial, reader, row["step"], packet))
    manuscript = book.chapter(db, row["chapter"], row["revision"])
    return {"packet": packet, "step": row["step"], "handle": panel["handle"], "sha256": row["digest"],
            "text": manuscript["body"].decode("utf-8")}


def _respond(db, args):
    row = db.execute("""SELECT c.*,p.digest FROM trial_copies c JOIN trial_plan p ON p.trial=c.trial AND p.step=c.step
                        WHERE c.packet=? AND c.trial=? AND c.reader=?""",
                     (args.packet, args.trial, args.reader.strip())).fetchone()
    if row is None or row["digest"] != args.sha256:
        raise ValueError("Packet, manuscript or recipient does not match this trial.")
    response = book.text_bytes(args.file.read_bytes())
    if row["response"] is not None:
        if (row["response"], row["stopped"]) != (response, args.stop):
            raise ValueError("The reader's original response is already frozen.")
    else:
        db.execute("UPDATE trial_copies SET response=?,stopped=? WHERE packet=?", (response, args.stop, args.packet))
    return {"recorded": args.packet, "step": row["step"], "stopped": args.stop}


def adopt_user_event(db, trial, event):
    """Record a decision already authenticated by the calling coordinator or host."""
    required = ("event_id", "run_key", "actor_role", "action", "chapter", "revision", "sha256")
    if not isinstance(event, dict) or any(k not in event for k in required):
        raise ValueError("User decision is missing required fields.")
    run_row = _run(db, trial)
    if (event["actor_role"] != "user" or event["action"] != "adopt-chapter"
            or event["run_key"] != run_row["run_key"] or not isinstance(event["event_id"], str)
            or not event["event_id"].strip() or run_row["evaluation"] is None):
        raise ValueError("Expected an explicit user decision about this evaluated trial.")
    ch, rev, digest = event["chapter"], event["revision"], event["sha256"]
    if type(ch) is not int or type(rev) is not int or not all(1 <= n <= 2**63-1 for n in (ch, rev)):
        raise ValueError("Invalid decision target.")
    if not isinstance(digest, str) or not db.execute("""SELECT 1 FROM trial_plan WHERE trial=? AND chapter=?
                                     AND revision=? AND digest=?""", (trial, ch, rev, digest)).fetchone():
        raise ValueError("Decision target was not a manuscript in this trial.")
    key = (trial, ch, rev, digest)
    previous = db.execute("SELECT trial,number,revision,digest FROM trial_decisions WHERE event_id=?",
                          (event["event_id"],)).fetchone()
    if previous is None:
        db.execute("INSERT INTO trial_decisions VALUES(?,?,?,?,?)", (event["event_id"], *key))
        db.execute("INSERT INTO adopted VALUES(?,?) ON CONFLICT(number) DO UPDATE SET revision=excluded.revision", (ch, rev))
    elif tuple(previous) != key:
        raise ValueError("User event is already bound to another decision.")
    current = db.execute("SELECT revision FROM adopted WHERE number=?", (ch,)).fetchone()
    return {"recorded_event": event["event_id"], "chapter": ch, "decision_revision": rev,
            "currently_adopted_revision": current[0] if current else None}


def run(db, args):
    action = args.trial_action
    if action == "create":
        return _create(db, args)
    if action == "next":
        return _next(db, args)
    if action == "respond":
        return _respond(db, args)
    status = _progress(db, args.trial)
    if action == "progress":
        return status
    if not status["closed"]:
        raise ValueError("Wait for each reader to finish or explicitly stop.")
    if action == "evaluate":
        text = book.text_bytes(args.file.read_bytes()).decode("utf-8")
        previous = _run(db, args.trial)["evaluation"]
        if previous is not None and previous != text:
            raise ValueError("The trial already has a frozen evaluation.")
        db.execute("UPDATE trial_runs SET evaluation=? WHERE id=?", (text, args.trial))
        return {"trial": args.trial, "evaluation_sha256": hashlib.sha256(text.encode()).hexdigest()}
    if action == "adopt":
        return adopt_user_event(db, args.trial, json.loads(args.user_event.read_bytes()))
    rows = db.execute("""SELECT c.step,c.reader,c.response,c.stopped,p.arm,p.chapter,p.revision,p.digest FROM trial_copies c
                         JOIN trial_plan p ON p.trial=c.trial AND p.step=c.step WHERE c.trial=?
                         ORDER BY c.step,c.reader""", (args.trial,))
    feedback = [{**dict(row), "response": row["response"].decode("utf-8"),
                 "stopped": None if status["origin"] == "historical" else bool(row["stopped"])} for row in rows]
    return {**status, "responses": feedback, "evaluation": _run(db, args.trial)["evaluation"]}
