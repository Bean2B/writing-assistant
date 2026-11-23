"""Offline and explicit local actor decisions for the World Sandbox."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from ..story import records, world
from . import tasks

COMMANDS = {"world-adapter"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS world_adapter_attempts (
    run TEXT NOT NULL, id TEXT NOT NULL, plan TEXT NOT NULL, digest TEXT NOT NULL,
    stage TEXT NOT NULL, attempt TEXT, fault TEXT, choice TEXT,
    PRIMARY KEY(run,id), FOREIGN KEY(run,id) REFERENCES world_requests(run,id)
);
"""


def register(subs):
    root = subs.add_parser("world-adapter", help="prepare and run an actor-scoped world decision")
    root.add_argument("--run", required=True)
    root.add_argument("--branch", default="main")
    sub = root.add_subparsers(dest="world_adapter_action", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("id")
    p.add_argument("--actor", required=True)
    p.add_argument("--expect", required=True, type=world.natural)
    p.add_argument("--runner", type=Path, help="freeze an explicit trusted local decision executable")
    p.add_argument("--timeout", type=tasks.positive, default=15)
    for name in ("inspect", "execute", "recover", "settle"):
        p = sub.add_parser(name)
        p.add_argument("id")
        if name != "inspect":
            p.add_argument("--expected-plan-sha256", required=True)
        if name == "execute":
            p.add_argument("--runner", type=Path)


def owner(db, args, action, **values):
    return world.run(db, argparse.Namespace(run=args.run, branch=args.branch, id=args.id, world_action=action, **values))


def row_for(db, args):
    row = db.execute("SELECT * FROM world_adapter_attempts WHERE run=? AND id=?", (args.run, args.id)).fetchone()
    if row is None:
        raise ValueError("Actor adapter plan unavailable.")
    plan = json.loads(row["plan"])
    if plan["branch"] != args.branch or records.checksum(row["plan"].encode()) != row["digest"]:
        raise ValueError("Actor adapter branch or plan identity differs.")
    if row["attempt"] is not None and not re.fullmatch(r"[0-9a-f]{32}", row["attempt"]):
        raise ValueError("Invalid actor attempt reference.")
    return row


def summary(db, args):
    row = row_for(db, args)
    return {"id": args.id, "plan_sha256": row["digest"], "adapter_stage": row["stage"],
            "world_stage": world.get_turn(db, args)["stage"], "choice": row["choice"], "fault": row["fault"]}


def actor_packet(db, args, turn):
    """Derive the permitted projection again before releasing anything to a runner."""
    spec, state, rev, _ = world.replay(db, args.run, args.branch, turn["revision"])
    actor = turn["actor"]
    allowed = {"actor_view": world.view(spec, state, actor),
               "actions": {key: a["label"] for key, a in world.choices(spec, state, actor).items()}}
    if rev != turn["revision"] or records.json_bytes(allowed) != turn["packet"]:
        raise ValueError("Saved request differs from the actor's permitted projection.")
    return allowed


def prepare(db, args):
    if args.timeout > 120:
        raise ValueError("Use a local decision timeout of at most 120 seconds.")
    runner_sha = tasks.runner_digest(args.runner) if args.runner else None
    owner(db, args, "request", actor=args.actor, expect=args.expect)
    turn = world.get_turn(db, args)
    packet = actor_packet(db, args, turn)
    plan = {"format": "writing-assistant/world-adapter-plan/1", "run": args.run, "id": args.id,
            "book_id": db.execute("SELECT book_id FROM writing_book_identity WHERE singleton=1").fetchone()[0],
            "branch": args.branch, "actor": args.actor, "revision": args.expect,
            "packet_sha256": records.checksum(records.json_bytes(packet)),
            "runner_sha256": runner_sha, "timeout": args.timeout}
    encoded = tasks.canonical(plan)
    sha = records.checksum(encoded.encode())
    if turn["stage"] != "prepared" and not db.execute(
            "SELECT 1 FROM world_adapter_attempts WHERE run=? AND id=?", (args.run, args.id)).fetchone():
        raise ValueError("The owner already dispatched this request through another route.")
    db.execute("""INSERT INTO world_adapter_attempts(run,id,plan,digest,stage) VALUES(?,?,?,?,'prepared')
                  ON CONFLICT(run,id) DO NOTHING""", (args.run, args.id, encoded, sha))
    tasks.expected(row_for(db, args), sha)
    return summary(db, args)


def result_path(directory, attempt):
    return tasks.private_dir(directory) / ("world-" + attempt + ".json")


class DecisionFailure(ValueError):
    """A bounded fault code safe to retain as the first observation."""


def finish(directory, args):
    path = None
    with tasks.connection(directory, True) as db:
        row = row_for(db, args)
        tasks.expected(row, args.expected_plan_sha256)
        if row["stage"] != "dispatching":
            return summary(db, args)
        plan = json.loads(row["plan"])
        try:
            turn = world.get_turn(db, args)
            packet = actor_packet(db, args, turn)
            if plan["packet_sha256"] != records.checksum(records.json_bytes(packet)):
                raise ValueError("Changed actor packet.")
            if plan["runner_sha256"] is None:
                choice = sorted(packet["actions"])[0]
            else:
                path = result_path(directory, row["attempt"])
                if path.is_symlink() or not path.is_file():
                    raise DecisionFailure("receipt_unavailable")
                stored = tasks.bounded_json(path, limit=16 * 1024 * 1024)
                if not isinstance(stored, dict):
                    raise DecisionFailure("invalid_receipt")
                if stored.get("failure") in ("adapter_timeout", "adapter_failed", "invalid_response", "response_limit",
                                             "adapter_os_error"):
                    raise DecisionFailure(stored["failure"])
                reply = stored.get("response")
                if (not isinstance(reply, dict) or set(reply) != {"format", "attempt", "choice"}
                        or reply["format"] != "writing-assistant/actor-choice/1" or reply["attempt"] != row["attempt"]):
                    raise DecisionFailure("invalid_receipt")
                choice = reply["choice"]
            if not isinstance(choice, str) or choice not in packet["actions"]:
                raise DecisionFailure("choice_not_offered")
            if turn["stage"] != "dispatching":
                raise ValueError("The owner already resolved this turn through another route.")
            owner(db, args, "result", choice=choice)
            db.execute("UPDATE world_adapter_attempts SET stage='result-recorded',choice=? WHERE run=? AND id=?",
                       (choice, args.run, args.id))
        except (ValueError, OSError, RecursionError) as error:
            fault = str(error) if isinstance(error, DecisionFailure) else "decision_unconfirmed"
            db.execute("UPDATE world_adapter_attempts SET stage='uncertain',fault=? WHERE run=? AND id=?",
                       (fault, args.run, args.id))
        result = summary(db, args)
    if path and result["adapter_stage"] == "result-recorded":
        path.unlink(missing_ok=True)
    return result


def launch_or_recover(args):
    # A repeat never reserves a new attempt or enters the transport.
    with tasks.worker_lock(args.book) as lock:
        if args.world_adapter_action == "recover":
            return finish(args.book, args)
        with tasks.connection(args.book, True) as db:
            row = row_for(db, args)
            tasks.expected(row, args.expected_plan_sha256)
            if row["stage"] != "prepared":
                return summary(db, args)
            plan = json.loads(row["plan"])
            runner = tasks.executable(args.runner) if args.runner else None
            if (tasks.runner_digest(runner) if runner else None) != plan["runner_sha256"]:
                raise ValueError("Local decision transport differs from the prepared plan.")
            turn = world.get_turn(db, args)
            packet = actor_packet(db, args, turn)
            if records.checksum(records.json_bytes(packet)) != plan["packet_sha256"]:
                raise ValueError("Actor inputs changed since preparation.")
            owner(db, args, "dispatching")
            attempt = uuid.uuid4().hex
            db.execute("UPDATE world_adapter_attempts SET attempt=?,stage='dispatching' WHERE run=? AND id=?",
                       (attempt, args.run, args.id))
        if runner:
            request = {"format": "writing-assistant/actor-decision/1", "attempt": attempt, **packet}
            worker = Path(__file__).with_name("task_worker.py")
            # A world executable receives no provider key, account handle, application path or session input.
            env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TMPDIR") if k in os.environ}
            try:
                subprocess.run([sys.executable, "-I", str(worker), str(runner), str(result_path(args.book, attempt)),
                                str(plan["timeout"])], pass_fds=(lock,), start_new_session=True, env=env,
                               input=records.json_bytes(request), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass  # Recovery observes the existing claim; it cannot launch a replacement.
        return finish(args.book, args)


def execute(args):
    action = args.world_adapter_action
    if action in ("execute", "recover"):
        return launch_or_recover(args)
    with tasks.connection(args.book, action != "inspect") as db:
        if action == "prepare":
            return prepare(db, args)
        if action == "settle":
            row = row_for(db, args)
            tasks.expected(row, args.expected_plan_sha256)
            if row["stage"] not in ("result-recorded", "settled"):
                raise ValueError("Settlement requires a validated actor result.")
            receipt = owner(db, args, "settle")
            db.execute("UPDATE world_adapter_attempts SET stage='settled' WHERE run=? AND id=?", (args.run, args.id))
            return {**summary(db, args), "settlement": receipt}
        return summary(db, args)


def exit_status(args, result):
    if args.command == "world-adapter" and args.world_adapter_action in ("execute", "recover"):
        return 2 if result["adapter_stage"] == "uncertain" else 0
    return 0
