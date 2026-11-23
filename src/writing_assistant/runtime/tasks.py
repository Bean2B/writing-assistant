"""Book-scoped, immutable model task plans and local process execution."""
import argparse
from contextlib import ExitStack, closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid

from .. import book
from ..filesystem import exclusive_file, linked
from ..story import chapter_cards, records
from .task_worker import MAX_RESPONSE

WINDOWS_PROCESS_ENV = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT"} if os.name == "nt" else set()

COMMANDS = {"task", "workflow"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_tasks (
    id TEXT PRIMARY KEY, plan TEXT NOT NULL, digest TEXT NOT NULL,
    state TEXT NOT NULL, attempt TEXT UNIQUE, response TEXT, fault TEXT, result TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS wa_task_capacity ON wa_tasks((1)) WHERE state='running';
CREATE TABLE IF NOT EXISTS wa_workflows (id TEXT PRIMARY KEY, plan TEXT NOT NULL, digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wa_workflow_steps (
    workflow TEXT REFERENCES wa_workflows(id), step INTEGER NOT NULL, task TEXT UNIQUE REFERENCES wa_tasks(id),
    PRIMARY KEY(workflow,step)
);
"""
PROVIDERS = ("codex", "deepseek", "claude", "gemini")
TASTES = {"人物读者": "更留意人物之间的感情和关系。", "行动读者": "更关心选择、行动和后果。", "氛围读者": "更留意气氛和未解的问题。"}
READING_QUESTION = "读完这章，你在意谁，期待什么，还想接着读吗？如果停下了，记下停在哪里。"


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def positive(value):
    n = int(value)
    if not 0 < n < 2**63:
        raise argparse.ArgumentTypeError("Expected a positive 64-bit integer.")
    return n


def options(parser, prefix=""):
    opt = "--" + prefix
    parser.add_argument(opt + "provider", choices=PROVIDERS, required=True)
    parser.add_argument(opt + "model", required=True)
    parser.add_argument(opt + "effort", default="high")
    parser.add_argument(opt + "runner", type=Path, help="trusted executable implementing the local JSON protocol")
    parser.add_argument(opt + "timeout", type=positive, default=120)


def register(subs):
    actions = subs.add_parser("task", help="prepare, execute and recover book-scoped tasks").add_subparsers(
        dest="task_action", required=True)
    p = actions.add_parser("prepare-write")
    p.add_argument("id")
    p.add_argument("number", type=positive)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--goal")
    source.add_argument("--prepared", type=Path, help="revalidate a targeted prepare packet from this book")
    p.add_argument("--material", action="append", default=[], help="explicit Creative Record ref")
    options(p)
    p = actions.add_parser("prepare-review")
    p.add_argument("id")
    p.add_argument("--packet", required=True)
    options(p)
    for name in ("inspect", "output", "execute", "receive", "recover", "close-uncertain"):
        p = actions.add_parser(name)
        p.add_argument("id")
        if name == "inspect":
            p.add_argument("--include-context", action="store_true", help="show the complete book-local frozen plan")
        if name in ("execute", "receive", "recover", "close-uncertain"):
            p.add_argument("--expected-plan-sha256", required=True)
        if name == "execute":
            p.add_argument("--runner", type=Path, help="use the exact executable frozen at prepare time")
        if name == "receive":
            p.add_argument("--file", type=Path, required=True, help="desktop bridge response JSON")

    flow = subs.add_parser("workflow", help="advance an ordered writing and reader sequence").add_subparsers(
        dest="workflow_action", required=True)
    p = flow.add_parser("create")
    p.add_argument("id")
    p.add_argument("--start", type=positive, required=True)
    p.add_argument("--chapters", type=positive, required=True)
    p.add_argument("--goal", required=True)
    p.add_argument("--readers", nargs="+", required=True)
    p.add_argument("--material", action="append", default=[])
    options(p, "writer-")
    options(p, "reader-")
    for name in ("inspect", "next"):
        p = flow.add_parser(name)
        p.add_argument("id")
        if name == "next":
            p.add_argument("--expected-plan-sha256", required=True)


@contextmanager
def connection(directory, writable=False):
    with closing(book.connect(directory, writable=writable)) as db, db:
        yield db


def required(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A nonempty name or text is required.")
    return value


def executable(path):
    if path is None:
        raise ValueError("Supply the trusted runner selected at task preparation.")
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Runner must be an executable file.")
    if os.name == "nt" and path.suffix.lower() not in (".exe", ".py") and path.name != "writing-assistant-provider":
        raise ValueError("Choose a native .exe, Python .py, or the bundled provider runner on Windows.")
    return path


def runner_digest(path):
    with executable(path).open("rb") as stream:
        sha = hashlib.sha256()
        for chunk in iter(lambda: stream.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def profile(args, prefix=""):
    runner = getattr(args, prefix + "runner")
    timeout = getattr(args, prefix + "timeout")
    if timeout > 600:
        raise ValueError("Local runner timeout must be at most 600 seconds.")
    return {
        "provider": getattr(args, prefix + "provider"),
        "model": required(getattr(args, prefix + "model")),
        "effort": required(getattr(args, prefix + "effort")),
        "runner_sha256": runner_digest(runner) if runner else None,
        "timeout_seconds": timeout,
    }


def task_row(db, ident):
    row = db.execute("SELECT * FROM wa_tasks WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise ValueError("Task not found.")
    if digest(row["plan"].encode()) != row["digest"]:
        raise ValueError("Task plan digest mismatch.")
    if row["attempt"] is not None and not re.fullmatch(r"[0-9a-f]{32}", row["attempt"]):
        raise ValueError("Invalid local attempt reference.")
    return row


def summary(row):
    plan = json.loads(row["plan"])
    config = plan["profile"]
    response = json.loads(row["response"]) if row["response"] else {}
    return {"id": row["id"], "plan_sha256": row["digest"], "state": row["state"],
            "role": plan["role"], "chapter": plan["target"], "reader": plan.get("reader"),
            "provider": config["provider"], "model": config["model"], "effort": config["effort"],
            "transport": "runner" if config["runner_sha256"] else "desktop",
            "fault": row["fault"], "usage": response.get("usage"),
            "session": response.get("session"),
            "result": json.loads(row["result"]) if row["result"] else None}


def expected(row, sha):
    if row["digest"] != sha:
        raise ValueError("Unexpected plan SHA-256.")


def prepare(db, ident, plan):
    required(ident)
    plan["task_id"] = ident
    frozen = canonical(plan)
    size = len(frozen.encode())
    if size > 4 * 1024 * 1024:
        raise ValueError("Selected task input exceeds 4 MiB.")
    sha = digest(frozen.encode())
    db.execute("INSERT INTO wa_tasks(id,plan,digest,state) VALUES(?,?,?,'prepared') ON CONFLICT(id) DO NOTHING",
               (ident, frozen, sha))
    row = task_row(db, ident)
    expected(row, sha)
    return summary(row)


def target_tip(db, n):
    return db.execute("SELECT coalesce(max(revision),0) FROM chapters WHERE number=?", (n,)).fetchone()[0]


def selected_packet(db, number, path):
    supplied = bounded_json(path, limit=4 * 1024 * 1024)
    if (not isinstance(supplied, dict) or supplied.get("phase") not in ("draft", "revise")
            or type(supplied.get("target_chapter")) is not int or supplied["target_chapter"] != number
            or not isinstance(supplied.get("materials"), list)):
        raise ValueError("A targeted draft or revision packet from this book is required.")
    prior, materials, current = [], [], None
    for item in supplied["materials"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid preparation input.")
        role = item.get("role")
        if role == "record":
            materials.append(required(item.get("ref")))
        elif role in ("current-draft", "prior-prose"):
            n, r = item.get("chapter"), item.get("revision")
            if any(type(v) is not int or not 0 < v < 2**63 for v in (n, r)):
                raise ValueError("Invalid selected chapter reference.")
            if role == "current-draft":
                if current is not None or n != number or r != book.chapter(db, n)["revision"]:
                    raise ValueError("Selected current draft or target has changed.")
                current = (n, r)
            elif n < number:
                prior.append((n, r))
            else:
                raise ValueError("Prior chapter must precede this target.")
        else:
            raise ValueError("Unknown preparation material role.")
    request = argparse.Namespace(request=required(supplied.get("request")), phase=supplied["phase"], target=number,
                                 chapter=current, prior=prior, material=materials, max_bytes=4 * 1024 * 1024)
    expected_packet = records.prepare(db, request)
    if canonical(supplied) != canonical(expected_packet):
        raise ValueError("Prepared material, book identity, settings or digest differs from this book.")
    return expected_packet


def write_plan(db, number, goal, config, materials, prepared_file=None):
    if prepared_file is None:
        context = book.handoff(db, number)
        selected = records.prepare(db, argparse.Namespace(request=goal, phase="draft", target=number, chapter=None,
                                                          prior=[], material=materials, max_bytes=4 * 1024 * 1024))
    else:
        if materials:
            raise ValueError("Use the material already frozen in the supplied packet.")
        selected = selected_packet(db, number, prepared_file)
        goal = selected["request"]
        context = {"next_chapter": number}
        # An external packet selects its own materials. Check that the target can be saved without reading other prose.
        first = db.execute("SELECT first_chapter FROM book").fetchone()[0]
        if number < first or (number > first and target_tip(db, number - 1) == 0):
            raise ValueError("Target cannot follow the book's existing chapters.")
    context.update({k: selected[k] for k in ("settings", "instructions", "materials", "phase")})
    return {"role": "writer", "goal": required(goal), "target": number, "profile": config,
            "output_format": "manuscript-and-card/1",
            "preparation_sha256": selected["sha256"], "target_tip": target_tip(db, number), "input": context}


def review_plan(db, packet_id, config):
    row = db.execute("SELECT * FROM packets WHERE id=?", (packet_id,)).fetchone()
    if row is None:
        raise ValueError("Reader packet not found in this book.")
    ch = book.chapter(db, row["number"], row["revision"])
    plan = {"role": "reader", "packet": packet_id, "reader": row["reader"], "session": row["handle"],
            "target": row["number"], "revision": row["revision"], "manuscript_sha256": ch["digest"],
            "profile": config, "input": {"text": ch["body"].decode(), "prompt": READING_QUESTION}}
    if row["handle"].startswith("local:" + config["provider"] + ":"):
        plan["input"]["taste"] = TASTES.get(row["reader"])
        history = db.execute("""SELECT f.number,f.response FROM feedback f JOIN packets p ON p.id=f.packet_id
                                WHERE f.reader=? AND p.handle=? AND f.number<? AND f.origin='reader-session'
                                ORDER BY f.number,f.revision""", (row["reader"], row["handle"], row["number"]))
        plan["input"]["earlier_responses"] = [{"chapter": past["number"], "response": past["response"].decode()}
                                               for past in history]
    verify_context(db, plan)
    return plan


def verify_context(db, plan):
    if plan["role"] == "reader":
        row = db.execute("SELECT handle FROM readers WHERE name=?", (plan["reader"],)).fetchone()
        if row is None or row[0] != plan["session"]:
            raise ValueError("Reader session binding changed.")
        previous = db.execute("SELECT 1 FROM feedback WHERE number=? AND revision=? AND reader=?",
                              (plan["target"], plan["revision"], plan["reader"])).fetchone()
        if previous:
            raise ValueError("This reader already replied to the selected chapter revision.")
    else:
        if target_tip(db, plan["target"]) != plan["target_tip"]:
            raise ValueError("Target chapter changed after preparation.")
        prior = plan["input"].get("previous_chapter")
        if prior and book.chapter(db, prior["number"])["revision"] != prior["revision"]:
            raise ValueError("Previous chapter selection changed after preparation.")


def envelope(row):
    plan = json.loads(row["plan"])
    p = plan["profile"]
    data = {"format": "writing-assistant/task-request/1", "task_id": row["id"], "attempt": row["attempt"],
            "plan_sha256": row["digest"], "provider": p["provider"], "model": p["model"],
            "effort": p["effort"], "role": plan["role"], "session": plan.get("session"), "input": plan["input"]}
    if plan["role"] == "writer":
        data["goal"] = plan["goal"]
        if "output_format" in plan:
            data["output_format"] = plan["output_format"]
    return data


def check_response(row, value):
    request = envelope(row)
    if not isinstance(value, dict) or value.get("format") != "writing-assistant/task-response/1":
        raise ValueError("Unsupported response format.")
    for key in ("task_id", "attempt", "plan_sha256", "provider", "model"):
        if value.get(key) != request[key]:
            raise ValueError("Response identity differs from the prepared task.")
    session = required(value.get("session"))
    if request["session"] is not None and session != request["session"]:
        raise ValueError("Response came from a different reader session.")
    text = required(value.get("text"))
    usage = value.get("usage")
    if usage is not None:
        if (not isinstance(usage, dict) or not usage or
                any(k not in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
                    or type(v) is not int or v < 0 for k, v in usage.items())):
            raise ValueError("Invalid reported token usage.")
    response = {"session": session, "text": text, "usage": usage}
    if "chapter_card" in value:
        if request["role"] != "writer" or not isinstance(value["chapter_card"], dict):
            raise ValueError("Only a writer can supply a chapter card object.")
        response["chapter_card"] = value["chapter_card"]
    return response


def capture(db, row, value):
    response = check_response(row, value)
    if "chapter_card" in response:
        chapter_cards.validate(db, response["chapter_card"], response["text"])
    captured = canonical(response)
    if row["response"] is not None:
        if row["response"] != captured:
            raise ValueError("A different response is already recorded.")
        return
    if row["state"] != "running":
        raise ValueError("Task does not have an outstanding attempt.")
    db.execute("UPDATE wa_tasks SET state='captured', response=? WHERE id=?", (captured, row["id"]))


def materialize(directory, ident):
    with connection(directory, True) as db:
        row = task_row(db, ident)
        if row["state"] == "captured":
            plan = json.loads(row["plan"])
            response = json.loads(row["response"])
            raw = response["text"].encode()
            db.execute("SAVEPOINT task_materialization")
            try:
                verify_context(db, plan)
                if plan["role"] == "writer":
                    result = book.save(db, plan["target"], raw)
                    if "chapter_card" in response:
                        result["card_version"] = chapter_cards.store(
                            db, plan["target"], result["revision"], response["chapter_card"], None)
                else:
                    result = book.feedback(db, plan["packet"], plan["manuscript_sha256"], raw)
                record = records.put_record(
                    db, name="task-" + row["attempt"], body=raw, operation="task-" + row["attempt"],
                    title=ident, category="manuscript" if plan["role"] == "writer" else "feedback",
                    audience="author", authorship="agent", origin=plan["profile"]["provider"],
                    source=canonical({"task_id": ident, "plan_sha256": row["digest"],
                                      "model": plan["profile"]["model"], "target": result}), parent=None)
                result["record_ref"] = record["ref"]
            except (ValueError, sqlite3.IntegrityError):
                db.execute("ROLLBACK TO task_materialization")
                db.execute("UPDATE wa_tasks SET fault='materialization_conflict' WHERE id=?", (ident,))
            else:
                db.execute("UPDATE wa_tasks SET state='completed', fault=NULL, result=? WHERE id=?",
                           (canonical(result), ident))
            finally:
                db.execute("RELEASE task_materialization")
        return summary(task_row(db, ident))


def private_dir(directory):
    path = directory.resolve() / ".writing-tasks"
    if linked(path):
        raise ValueError("Task receipt directory must be local to the book.")
    path.mkdir(mode=0o700, exist_ok=True)
    return path


@contextmanager
def worker_lock(directory):
    path = private_dir(directory) / "worker.lock"
    with ExitStack() as locks:
        try:
            handle = locks.enter_context(exclusive_file(path, wait=False))
        except BlockingIOError:
            raise ValueError("A local worker is still active.") from None
        yield handle


def dispatch_worker(handle, runner, path, timeout, request, environment):
    worker = Path(__file__).with_name("task_worker.py")
    command = [sys.executable, "-I", str(worker), str(runner), str(path), str(timeout)]
    options = {"pass_fds": (handle,), "start_new_session": True}
    if os.name == "nt":
        import _winapi
        process = _winapi.GetCurrentProcess()
        inherited = _winapi.DuplicateHandle(process, handle, process, 0, True, _winapi.DUPLICATE_SAME_ACCESS)
        startup = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [inherited]})
        options = {"startupinfo": startup, "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    try:
        subprocess.run(command, input=request, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=environment, **options)
    finally:
        if os.name == "nt":
            _winapi.CloseHandle(inherited)


def bounded_json(path, limit=MAX_RESPONSE):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON file exceeds the local size limit.")
    return json.loads(raw.decode("utf-8"))


def settle_local(directory, ident):
    with connection(directory, True) as db:
        row = task_row(db, ident)
        if row["state"] == "running":
            file = private_dir(directory) / (row["attempt"] + ".json")
            fault = "dispatch_uncertain"
            if file.is_file() and not linked(file):
                try:
                    # Worker writes only an atomically finished JSON result.
                    obj = json.loads(file.read_bytes())
                    if "response" in obj:
                        capture(db, row, obj["response"])
                        fault = None
                    elif obj.get("failure") in ("adapter_timeout", "response_limit", "adapter_failed",
                                               "invalid_response", "adapter_os_error"):
                        fault = obj["failure"]
                except (ValueError, TypeError, KeyError, RecursionError):
                    fault = "invalid_response"
            if fault:
                db.execute("UPDATE wa_tasks SET state='uncertain',fault=? WHERE id=?", (fault, ident))
    result = materialize(directory, ident)
    if result["state"] != "running":
        # The database now owns the successful response or terminal fault.
        file = private_dir(directory) / (row["attempt"] + ".json") if row["attempt"] else None
        if file and file.exists() and not linked(file):
            file.unlink(missing_ok=True)
    return result


def launch(args):
    with connection(args.book) as db:
        old = task_row(db, args.id)
        expected(old, args.expected_plan_sha256)
        config = json.loads(old["plan"])["profile"]
    if old["state"] != "prepared":
        return summary(old)
    local = config["runner_sha256"] is not None
    if (args.runner is not None) != local:
        raise ValueError("Execution transport differs from the prepared plan.")
    runner = executable(args.runner) if local else None
    if local and runner_digest(runner) != config["runner_sha256"]:
        raise ValueError("Runner differs from the prepared executable.")
    with worker_lock(args.book) as fd:
        with connection(args.book, True) as db:
            row = task_row(db, args.id)
            expected(row, args.expected_plan_sha256)
            if row["state"] != "prepared":
                return summary(row)
            plan = json.loads(row["plan"])
            verify_context(db, plan)
            if plan["role"] == "writer" and records.settings(db) != plan["input"]["settings"]:
                raise ValueError("Book settings changed after task preparation.")
            if db.execute("SELECT 1 FROM wa_tasks WHERE state='running'").fetchone():
                raise ValueError("Book task capacity is in use.")
            attempt = uuid.uuid4().hex
            db.execute("UPDATE wa_tasks SET state='running', attempt=? WHERE id=?", (attempt, args.id))
            row = task_row(db, args.id)
            request = envelope(row)
        if not local:
            return {**summary(row), "desktop_request": request}
        path = private_dir(args.book) / (attempt + ".json")
        try:
            portable = {"HOME", "PATH", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL"}
            secret = {"deepseek": "DEEPSEEK_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
            portable.update(WINDOWS_PROCESS_ENV)
            if os.name == "nt" and config["provider"] == "codex":
                portable.update({"USERPROFILE", "LOCALAPPDATA", "APPDATA"})
            portable.add(secret.get(config["provider"]))
            environment = {k: v for k, v in os.environ.items() if k in portable}
            dispatch_worker(fd, runner, path, config["timeout_seconds"], canonical(request).encode(), environment)
        except OSError:
            pass  # The persisted claim must be reconciled even when spawn fails.
        return settle_local(args.book, args.id)


def execute(args):
    if args.command == "workflow":
        from . import task_workflow
        return task_workflow.execute(args)
    action = args.task_action
    if action.startswith("prepare-"):
        config = profile(args)
        with connection(args.book, True) as db:
            plan = (write_plan(db, args.number, args.goal, config, args.material, args.prepared) if action == "prepare-write"
                    else review_plan(db, args.packet, config))
            return prepare(db, args.id, plan)
    if action == "execute":
        return launch(args)
    with connection(args.book, action in ("receive", "close-uncertain")) as db:
        row = task_row(db, args.id)
        plan = json.loads(row["plan"])
        if action == "inspect":
            info = summary(row)
            if args.include_context:
                info["plan"] = plan
            return info
        if action == "output":
            if not row["response"]:
                raise ValueError("Task has no captured output.")
            return json.loads(row["response"])["text"].encode()
        expected(row, args.expected_plan_sha256)
        if action == "close-uncertain":
            if plan["profile"]["runner_sha256"] is not None or row["state"] != "running":
                raise ValueError("Only outstanding desktop handoffs can be closed as uncertain.")
            db.execute("UPDATE wa_tasks SET state='uncertain',fault='unconfirmed_desktop_delivery' WHERE id=?", (args.id,))
            return summary(task_row(db, args.id))
        if action == "receive":
            if plan["profile"]["runner_sha256"] is not None:
                raise ValueError("Local execution requires the worker's own receipt.")
            capture(db, row, bounded_json(args.file))
    if action == "recover" and row["state"] == "running":
        with worker_lock(args.book):
            if plan["profile"]["runner_sha256"] is not None:
                return settle_local(args.book, args.id)
            # A recovered desktop envelope carries the same attempt ID. The host inspects its session before any delivery.
            return {**summary(row), "desktop_request": envelope(row)}
    return materialize(args.book, args.id)


def exit_status(args, result):
    """Execution mutations retain their structured receipt when local delivery failed."""
    if (args.command == "task" and args.task_action in ("execute", "receive", "recover")
            and (result.get("state") == "uncertain" or result.get("fault") == "materialization_conflict")):
        return 2
    return 0
