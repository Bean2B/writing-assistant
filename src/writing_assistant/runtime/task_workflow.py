"""Resume a bounded chapter and fixed-reader sequence by its frozen plan."""
import json

from .. import book
from ..story import records
from . import tasks


def workflow(db, ident):
    row = db.execute("SELECT * FROM wa_workflows WHERE id=?", (ident,)).fetchone()
    if row is None or tasks.digest(row["plan"].encode()) != row["digest"]:
        raise ValueError("Workflow not found or its saved plan differs from its digest.")
    return row


def steps(db, ident):
    return list(db.execute("""SELECT s.step,s.task,t.state,t.digest,t.result
                              FROM wa_workflow_steps s JOIN wa_tasks t ON t.id=s.task
                              WHERE s.workflow=? ORDER BY s.step""", (ident,)))


def view(db, row):
    plan = json.loads(row["plan"])
    rows = steps(db, row["id"])
    finished = sum(step["state"] == "completed" for step in rows)
    total = plan["chapters"] * (1 + len(plan["readers"]))
    return {"id": row["id"], "plan_sha256": row["digest"], "steps": total,
            "completed_steps": finished, "state": "completed" if finished == total else "open",
            "current_task": tasks.summary(tasks.task_row(db, rows[-1]["task"])) if rows else None}


def create(db, args):
    tasks.required(args.id)
    if (args.chapters > 200 or args.start + args.chapters - 1 >= 2**63 or
            not 1 <= len(args.readers) <= 10 or len(set(args.readers)) != len(args.readers)):
        raise ValueError("Use 1–200 chapters and 1–10 distinct registered readers.")
    roster = []
    for reader in args.readers:
        row = db.execute("SELECT handle FROM readers WHERE name=?", (reader,)).fetchone()
        if row is None or not row["handle"]:
            raise ValueError("Register an actual session handle for each workflow reader.")
        roster.append({"name": reader, "session": row["handle"]})
    plan = tasks.canonical({"id": args.id, "start": args.start, "chapters": args.chapters,
                            "goal": tasks.required(args.goal), "readers": roster,
                            "settings": records.settings(db), "materials": args.material,
                            "writer": tasks.profile(args, "writer_"), "reader": tasks.profile(args, "reader_")})
    sha = tasks.digest(plan.encode())
    db.execute("INSERT INTO wa_workflows VALUES(?,?,?) ON CONFLICT(id) DO NOTHING", (args.id, plan, sha))
    row = workflow(db, args.id)
    tasks.expected(row, sha)
    return view(db, row)


def advance(db, row):
    plan = json.loads(row["plan"])
    rows = steps(db, row["id"])
    idx = len(rows)
    width = 1 + len(plan["readers"])
    if (rows and rows[-1]["state"] != "completed") or idx == plan["chapters"] * width:
        return view(db, row)
    chapter_index, phase = divmod(idx, width)
    number = plan["start"] + chapter_index
    if phase:
        rec = plan["readers"][phase - 1]
        version = json.loads(rows[idx - phase]["result"])
        packet = book.packet(db, number, version["revision"], rec["name"])
        if packet["handle"] != rec["session"] or packet["sha256"] != version["sha256"]:
            raise ValueError("Current reader session or manuscript differs from the frozen workflow.")
        next_plan = tasks.review_plan(db, packet["packet"], plan["reader"])
    else:
        if idx:
            version = json.loads(rows[idx - width]["result"])
            if book.chapter(db, number - 1)["digest"] != version["sha256"]:
                raise ValueError("The previous draft has changed since the workflow's reader session.")
        if records.settings(db) != plan["settings"]:
            raise ValueError("Book settings changed after workflow creation.")
        next_plan = tasks.write_plan(db, number, plan["goal"], plan["writer"], plan["materials"])
    # Namespacing with the complete plan digest avoids collisions between books' workflows.
    ident = "workflow-" + row["digest"] + "-" + str(idx + 1)
    tasks.prepare(db, ident, next_plan)
    db.execute("INSERT INTO wa_workflow_steps VALUES(?,?,?)", (row["id"], idx + 1, ident))
    return view(db, row)


def execute(args):
    with tasks.connection(args.book, args.workflow_action != "inspect") as db:
        if args.workflow_action == "create":
            return create(db, args)
        row = workflow(db, args.id)
        if args.workflow_action == "inspect":
            return view(db, row)
        tasks.expected(row, args.expected_plan_sha256)
        return advance(db, row)
