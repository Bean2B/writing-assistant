"""Immutable prepared writing tasks and conservative local recovery.

RecordStore owns all bytes and versions. One local attempt is permitted per task;
reservation does not prove dispatch, provider completion, or provider-side stop.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import stat
from time import monotonic

from . import __version__
from .adapters import codex
from .core.config import snapshot
from .core.errors import AssistantError, require
from .core.interface import IDENTIFIER, prepare as prepare_packet, validate_request
from .core.jsonio import MAX_BYTES, canonical, decode, digest, fields
from .records.application import owner_store
from .records.core import RecordsError, ref_key
from .execution import (_capture, _diagnostic_context, _diagnostic_failure, _diagnostic_preflight,
                        _id, _materialize, _run, _writing_relations, writing_prompt)

CONTRACT = "writing-assistant-task/1"
EXECUTION_POLICY = "writing-assistant-execution/1"
DEFAULT_LIMITS = {"max_attempts": 1, "max_prompt_bytes": MAX_BYTES,
                  "max_material_bytes": MAX_BYTES, "max_output_bytes": codex.FINAL_LIMIT}
_PARTS = ("input", "stdout", "stderr", "output")


def _task_id(value):
    require(type(value) is str and IDENTIFIER.fullmatch(value), "invalid_identifier")
    return value


def _operation(scope, task_id, part):
    return _id(scope.project_id, task_id, "task-" + part)


def _lookup(store, scope, task_id, part, *, body=True):
    return store.operation(scope, _operation(scope, task_id, part), include_body=body)


def _save(store, scope, task_id, part, body, *, related=()):
    return store.save(scope, operation_id=_operation(scope, task_id, part), body=body,
                      kind="decision" if part != "prompt" else "fragment",
                      title="Writing task " + part, related=related,
                      source={"authorship": "unknown", "origin": "Local writing task; no adoption authority"})


_TIMING_SLOTS = ("preflight", "execute", "reconcile")
_TIMING_SCOPE = "local_task_operation_before_timing_persistence"


def _timing_views(store, scope, task_id, plan_ref):
    from .output_contracts import valid_operation_timings
    result = {}
    for slot in _TIMING_SLOTS:
        saved = _lookup(store, scope, task_id, "timing-" + slot)
        if saved is None:
            continue
        value = decode(saved["body"])
        required = {"contract", "plan_sha256", "sample", "operation", "elapsed_seconds", "clock", "scope", "outcome"}
        require(type(value) is dict and required <= set(value) <= required | {"code"}
                and value.get("plan_sha256") == plan_ref["sha256"]
                and value.get("contract") == "writing-assistant-operation-timing/1"
                and value.get("operation") == ("task reconcile" if slot == "reconcile" else "task execute"),
                "invalid_task_evidence")
        result[slot] = {key: item for key, item in value.items()
                        if key not in {"contract", "plan_sha256"}}
        result[slot].update(status="recorded", record=saved["ref"])
        require(valid_operation_timings({slot: result[slot]}), "invalid_task_evidence")
    return result


def _record_timing(store, scope, task_id, plan_ref, slot, elapsed, outcome, code=None):
    # Fixed slots retain first observations and bound growth across repeated calls.
    if _lookup(store, scope, task_id, "timing-" + slot, body=False) is not None:
        return
    value = {"contract": "writing-assistant-operation-timing/1", "plan_sha256": plan_ref["sha256"],
             "sample": "first_observed", "operation": "task reconcile" if slot == "reconcile" else "task execute",
             "elapsed_seconds": elapsed, "clock": "monotonic", "scope": _TIMING_SCOPE, "outcome": outcome}
    if code is not None and type(code) is str and 0 < len(code) <= 128 and all(
            c in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in code):
        value["code"] = code
    _save(store, scope, task_id, "timing-" + slot, canonical(value), related=[plan_ref])


def _finish_timing(store, scope, task_id, plan_ref, slot, started, result):
    # Core result/raw capture/materialization and final receipt writes have ended.
    # Telemetry publication and transport are explicitly outside this interval.
    elapsed = max(0.0, monotonic() - started)
    try:
        _record_timing(store, scope, task_id, plan_ref, slot, elapsed, result["status"], result.get("code"))
    except (RecordsError, OSError) as error:
        if isinstance(error, RecordsError) and error.code not in {"storage_error", "outcome_unknown", "busy"}:
            raise
        # A telemetry I/O failure must not turn a completed effect into a resend.
        return _mutation_receipt(store, scope, task_id,
                                 {**result, "timing_recording": {"status": "unavailable", "code": "timing_recording_failed"}})
    timings = _timing_views(store, scope, task_id, plan_ref)
    if timings:
        result = {**result, "operation_timings": timings}
    return _mutation_receipt(store, scope, task_id, result)


def _failed_timing(store, scope, task_id, plan_ref, slot, started, error):
    elapsed = max(0.0, monotonic() - started)
    try:
        if store.operation(scope, _id(scope.project_id, task_id, "intent"), include_body=False) is not None:
            _record_timing(store, scope, task_id, plan_ref, slot, elapsed, "error",
                           getattr(error, "code", "local_input_error"))
    except (AssistantError, RecordsError, OSError):
        # The original error (including authority/integrity failures) stays primary.
        # An unavailable timing record never authorizes another dispatch.
        pass


def _identity(store, scope):
    with store.session(scope) as io:
        row = os.fstat(io.directory(()))
        return [row.st_dev, row.st_ino]


def _policy():
    # Bind installed application behavior as well as its explicit protocol.
    # These are application source bytes, never environment values or user data.
    base = Path(__file__).parent
    names = ("__init__.py", "tasks.py", "execution.py", "core/interface.py", "core/config.py", "core/files.py",
             "core/jsonio.py", "core/errors.py", "frameworks.py", "adapters/codex.py",
             "records/core.py", "records/application.py", "records/adapters.py", "records/safeio.py", "records/bounded_io.py")
    sources = {name: digest((base / name).read_bytes()) for name in names}
    for name in ("diagnostics.py", "output_contracts.py", "techniques.py"):
        optional = base / name
        if optional.is_file():
            sources[name] = digest(optional.read_bytes())
    from .techniques import source_digests
    sources.update(source_digests())
    producer = base.parent / "writing_frameworks"
    for path in sorted(producer.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".md"}:
            sources["writing_frameworks/" + path.relative_to(producer).as_posix()] = digest(path.read_bytes())
    return {"version": EXECUTION_POLICY, "package_version": __version__,
            "source_sha256": sources,
            "stream_limit": codex.STREAM_LIMIT, "final_limit": codex.FINAL_LIMIT}


def _limits(value):
    result = dict(DEFAULT_LIMITS) if value is None else value
    fields(result, DEFAULT_LIMITS)
    for key, maximum in DEFAULT_LIMITS.items():
        require(type(result[key]) is int and 0 < result[key] <= maximum, "invalid_task_limits")
    require(result["max_attempts"] == 1, "invalid_task_limits")
    return dict(result)


def _selection(store, scope, request, bindings, ranges, limit, resolver=None):
    require(isinstance(bindings, (list, tuple)) and len(bindings) <= 32, "invalid_task_bindings")
    require(isinstance(ranges, (list, tuple)) and len(ranges) <= 32, "invalid_task_ranges")
    selected, spans, bodies = {}, {}, {}
    for binding in bindings:
        fields(binding, ("uri", "ref"))
        require(type(binding["uri"]) is str and binding["uri"] not in selected, "invalid_task_bindings")
        ref_key(binding["ref"])
        selected[binding["uri"]] = binding["ref"]
    for span in ranges:
        fields(span, ("uri", "start", "end"))
        require(type(span["uri"]) is str and span["uri"] not in spans, "invalid_task_ranges")
        require(type(span["start"]) is int and type(span["end"]) is int
                and 0 <= span["start"] <= span["end"], "invalid_task_ranges")
        spans[span["uri"]] = span
    uris = {item["uri"] for item in request["materials"]}
    require(set(selected) == uris and set(spans) <= uris, "task_scoped_binding_required")
    total = 0
    for material in request["materials"]:
        uri = material["uri"]
        raw = store.read(scope, selected[uri])["body"]
        if resolver is not None:
            # Existing material_resolver authenticates the complete original;
            # the packet's material hash below identifies only the selected span.
            original = {**material, "sha256": selected[uri]["sha256"]}
            require(resolver(original) == raw, "changed_reference")
        if uri in spans:
            span = spans[uri]
            require(span["end"] <= len(raw), "invalid_task_ranges")
            raw = raw[span["start"]:span["end"]]
        total += len(raw)
        require(total <= limit, "input_limit")
        require(digest(raw) == material["sha256"], "changed_reference")
        try:
            raw.decode("utf-8")
        except UnicodeError:
            raise AssistantError("invalid_material_encoding") from None
        bodies[uri] = raw
    return bodies


def _load(store, scope, task_id):
    saved = _lookup(store, scope, task_id, "plan")
    require(saved is not None, "task_not_found")
    plan = decode(saved["body"])
    require(plan.get("contract") == CONTRACT and plan.get("task_id") == task_id
            and plan.get("project_id") == scope.project_id, "invalid_task_plan")
    require(saved["body"] == canonical(plan), "invalid_task_plan")
    require(plan["request"]["request_id"] == task_id, "invalid_task_plan")
    return plan, saved["ref"]


@contextmanager
def _lock(store, scope, task_id):
    # Keep the lock inode in the authenticated RecordStore namespace. It is
    # independent of the short project publication lock used by RecordStore.save.
    application_error = None
    with store.session(scope, write=True) as io:
        # Provider execution is bounded separately at 600 seconds. Do not apply
        # the short record transaction deadline to the held per-task lock.
        io.budget.deadline += 600
        parts = tuple((store.project(scope) + "/task-locks").split("/"))
        io.directory(parts, create=True)
        parent = io.directory(parts)
        name = task_id + ".lock"
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        held = False
        try:
            row = os.fstat(fd)
            require(stat.S_ISREG(row.st_mode) and row.st_nlink == 1, "invalid_task_lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AssistantError("busy") from None
            held = True
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require((row.st_dev, row.st_ino) == (current.st_dev, current.st_ino), "invalid_task_lock")
            scope.verify(write=True)
            yield
        except AssistantError as error:
            # RecordStore sessions intentionally normalize arbitrary ValueError;
            # preserve the task layer's already-safe application error codes.
            application_error = error
        finally:
            if held:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    if application_error is not None:
        raise application_error


def prepare(project, request, *, bindings=(), resolver=None, model=None, reasoning_effort=None, timeout=120,
            limits=None, ranges=(), artifact_resolver=None):
    """Persist an exact plan; no provider qualification, process, or model call."""
    request = decode(canonical(request))
    validate_request(request)
    require(request["kind"] == "writing", "unsupported_request_kind")
    task_id = request["request_id"]
    codex.validate_options(model, timeout, reasoning_effort=reasoning_effort)
    limits = _limits(limits)
    require(isinstance(bindings, (list, tuple)) and isinstance(ranges, (list, tuple)), "invalid_task_bindings")
    bindings, ranges = decode(canonical(list(bindings))), decode(canonical(list(ranges)))
    configuration = snapshot(project)
    require(resolver is None or callable(resolver), "scoped_resolver_required")
    store, scope = owner_store(project, write=True, resolver=artifact_resolver)
    existing = _lookup(store, scope, task_id, "plan")
    if existing is not None:
        prior = decode(existing["body"])
        require(_identity(store, scope) == prior["data_root_identity"], "authority_changed")
        require(all(prior[key] == value for key, value in
                    (("request", request), ("bindings", bindings), ("ranges", ranges),
                     ("model", model), ("timeout", timeout), ("limits", limits))), "task_conflict")
        require(prior.get("reasoning_effort") == reasoning_effort, "task_conflict")
    bodies = None

    def resolve(reference):
        nonlocal bodies
        if bodies is None:
            # Packet validators own configuration, phase and relation rules.
            # Resolve selected bytes only after those content-free checks pass.
            bodies = _selection(store, scope, request, bindings, ranges,
                                limits["max_material_bytes"], resolver)
        return bodies[reference["uri"]]

    packet = prepare_packet(request, configuration, resolver=resolve)
    if bodies is None:
        # Empty requests still validate empty bindings/ranges after the packet
        # checks, without creating a second set of phase or relation rules.
        _selection(store, scope, request, bindings, ranges, limits["max_material_bytes"], resolver)
    relations = _writing_relations(store, scope, request, bindings, ranges)
    prompt = writing_prompt(packet)
    require(len(prompt) <= limits["max_prompt_bytes"], "input_limit")
    parent, work_id = None, None
    if request.get("phase") == "revise":
        drafts = [item for item in request["materials"] if item.get("role") == "current-draft"]
        require(len(drafts) == 1, "invalid_revision_target")
        parent = next(item["ref"] for item in bindings if item["uri"] == drafts[0]["uri"])
        work_id = store.read(scope, parent)["metadata"]["work_id"]
    plan = {"contract": CONTRACT, "task_id": task_id, "project_id": scope.project_id,
            "attempt_id": _operation(scope, task_id, "attempt"), "request": request,
            "bindings": bindings, "ranges": ranges, "configuration": configuration,
            "data_root_identity": _identity(store, scope), "policy": _policy(),
            "model": model, "model_selection_source": "explicit-command" if model is not None
            else "codex-cli-default-user-config-ignored",
            "reasoning_effort": reasoning_effort, "reasoning_effort_selection_source":
            "explicit-command" if reasoning_effort is not None else "codex-cli-default-user-config-ignored", "timeout": timeout,
            "limits": limits, "packet": packet, "prompt_sha256": digest(prompt),
            "parent": parent, "work_id": work_id, "relations": relations}
    raw = canonical(plan)
    require(len(raw) <= MAX_BYTES, "input_limit")
    with _lock(store, scope, task_id):
        existing = _lookup(store, scope, task_id, "plan")
        if existing is not None:
            require(existing["body"] == raw, "task_conflict")
        else:
            require(store.operation(scope, _id(scope.project_id, task_id, "intent"), include_body=False)
                    is None, "legacy_request_reserved")
            scope.verify(write=True)
            require(snapshot(project) == configuration, "changed_configuration")
            try:
                prompt_ref = _save(store, scope, task_id, "prompt", prompt)["ref"]
                _save(store, scope, task_id, "plan", raw, related=[prompt_ref])
            except RecordsError as error:
                if error.code == "operation_conflict":
                    raise AssistantError("task_conflict") from None
                raise
    return _mutation_receipt(store, scope, task_id, _view(store, scope, task_id))


def _view(store, scope, task_id):
    plan, ref = _load(store, scope, task_id)
    require(_identity(store, scope) == plan["data_root_identity"], "authority_changed")
    receipt = _lookup(store, scope, task_id, "receipt")
    descriptor = _lookup(store, scope, task_id, "result")
    intent = store.operation(scope, _id(scope.project_id, task_id, "intent"), include_body=False)
    partial = {}
    for part in _PARTS + ("observation",):
        found = store.operation(scope, _id(scope.project_id, task_id, part), include_body=False)
        if found is not None:
            partial[part] = found["ref"]
    status, model_status, local_status = "prepared", "not_dispatched", "not_started"
    result = None
    if intent is not None:
        status, model_status = "uncertain", "unknown"
    if descriptor is not None:
        observed = decode(descriptor["body"])
        require(observed["plan_sha256"] == ref["sha256"], "invalid_task_evidence")
        status, model_status, local_status = "model_recorded", observed["result"]["status"], "pending"
        if set(partial) != set(_PARTS + ("observation",)):
            status = "result_incomplete"
    if receipt is not None:
        result = decode(receipt["body"])
        require(result["plan_sha256"] == ref["sha256"], "invalid_task_evidence")
        status, model_status, local_status = result["state"], result["model_status"], result["materialization_status"]
        if set(partial) != set(_PARTS + ("observation",)):
            status = "result_incomplete"
    diagnostic_summary = None
    if descriptor is not None:
        preflight = observed["result"].get("diagnostics_preflight", {})
        diagnostic_summary = {key: preflight.get(key) for key in ("coverage", "warnings", "blocking", "decision")}
    timings = _timing_views(store, scope, task_id, ref)
    return {"contract": CONTRACT, "task_id": task_id, "attempt_id": plan["attempt_id"],
            "plan_sha256": ref["sha256"], "plan": ref, "status": status,
            "model_status": model_status, "materialization_status": local_status,
            "evidence": partial, "result": result, "adopted": False,
            **({"operation_timings": timings} if timings else {}),
            "phase": plan["request"].get("phase", "draft"), "bindings": plan["bindings"],
            "ranges": plan["ranges"], "relations": plan["relations"],
            "diagnostics": diagnostic_summary,
            "model_requested": plan["model"], "reasoning_effort_requested": plan.get("reasoning_effort"),
            "actions": ["execute"] if status == "prepared" else
            ["inspect"] if receipt is not None or descriptor is None else ["reconcile"],
            "model_calls": 0}


def _mutation_receipt(store, scope, task_id, view):
    """Keep successful local effects recoverable when their full view is large."""
    required_bytes = len(canonical(view)) + 1
    if required_bytes <= 32768:
        return view
    retained = ("contract", "task_id", "attempt_id", "plan_sha256", "plan", "status", "model_status",
                "materialization_status", "evidence", "adopted", "phase", "model_requested",
                "reasoning_effort_requested", "actions", "model_calls", "dispatch_attempts", "code", "qualification",
                "operation_timings", "timing_recording")
    compact = {key: view[key] for key in retained if key in view}
    details = {"inspect_required_bytes": required_bytes}
    for part in ("result", "receipt"):
        saved = _lookup(store, scope, task_id, part, body=False)
        if saved is not None:
            details[part] = saved["ref"]
    if type(view.get("diagnostics")) is dict:
        compact["diagnostics_summary"] = {key: view["diagnostics"][key] for key in
            ("coverage", "blocking", "decision", "history", "warnings", "primary_code") if key in view["diagnostics"]}
        details["diagnostics_operation"] = "task diagnostics"
    compact.update(view="compact", omitted_fields=sorted(set(view) - set(compact)), details=details)
    require(len(canonical(compact)) + 1 <= 32768, "output_limit")
    return compact


def _local_runtime(store, scope, task_id):
    """Observe a reserved task's local lock, without contacting its provider."""
    intent = store.operation(scope, _id(scope.project_id, task_id, "intent"), include_body=False)
    require(intent is not None, "invalid_task_evidence")
    lock_state = "missing"
    with store.session(scope) as io:
        parts = tuple((store.project(scope) + "/task-locks").split("/"))
        try:
            parent = io.directory(parts)
            fd = os.open(task_id + ".lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
        except FileNotFoundError:
            pass
        else:
            held = False
            try:
                row = os.fstat(fd)
                if not stat.S_ISREG(row.st_mode) or row.st_nlink != 1:
                    raise RecordsError("invalid_task_lock")
                try:
                    # An exclusive task operation blocks this shared probe.
                    # No PID, lock-file contents or stale owner marker is used.
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    held, lock_state = True, "available"
                except BlockingIOError:
                    lock_state = "held"
                current = os.stat(task_id + ".lock", dir_fd=parent, follow_symlinks=False)
                if (row.st_dev, row.st_ino) != (current.st_dev, current.st_ino):
                    raise RecordsError("invalid_task_lock")
                scope.verify()
            finally:
                if held:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
    now = datetime.now(timezone.utc)
    received_at = intent["metadata"]["received_at"]
    seconds = (now - datetime.fromisoformat(received_at)).total_seconds()
    return {"state": {"held": "local_operation_active", "available": "no_local_operation_observed",
                      "missing": "unknown"}[lock_state],
            "task_lock": lock_state, "observed_at": now.isoformat(),
            "reservation_received_at": received_at,
            "seconds_since_reservation": round(seconds, 3) if seconds >= 0 else None,
            "backend_status": "unknown"}


def inspect(project, task_id, *, include_context=False, max_bytes=32768):
    """Return saved facts and a bounded local lock observation; no provider work."""
    _task_id(task_id)
    store, scope = owner_store(project)
    require(type(include_context) is bool and type(max_bytes) is int
            and 1024 <= max_bytes <= MAX_BYTES, "invalid_task_limits")
    result = _view(store, scope, task_id)
    if result["status"] == "uncertain":
        result["local_runtime"] = _local_runtime(store, scope, task_id)
    if include_context:
        plan, _ = _load(store, scope, task_id)
        context = {"request": None, "materials": [], "omitted": []}
        result["context"] = context
        context["request"] = plan["request"]["request"]
        if len(canonical(result)) > max_bytes:
            context["request"] = None
            context["omitted"].append({"kind": "request", "reason": "byte_limit"})
        for item in plan["packet"]["materials"]:
            context["materials"].append(item)
            if len(canonical(result)) > max_bytes:
                context["materials"].pop()
                context["omitted"].append({"uri": item["reference"]["uri"], "reason": "byte_limit"})
    require(len(canonical(result)) + 1 <= max_bytes, "output_limit")
    return result


def _plan_binding(project, store, scope, plan, *, write=False):
    scope.verify(write=write)
    require(_identity(store, scope) == plan["data_root_identity"], "authority_changed")
    require(snapshot(project) == plan["configuration"], "stale_plan")
    require(_policy() == plan["policy"], "stale_plan")
    _limits(plan["limits"])
    codex.validate_options(plan["model"], plan["timeout"], reasoning_effort=plan.get("reasoning_effort"))
    for binding in plan["bindings"]:
        store.read(scope, binding["ref"], include_body=False)
    prompt = _lookup(store, scope, plan["task_id"], "prompt", body=False)
    require(prompt is not None and prompt["ref"]["sha256"] == plan["prompt_sha256"], "invalid_task_plan")


def diagnostic_context(project, task_id, *, expected_plan_sha256, include_preflight=False,
                       max_bytes=32768):
    """Return safe task-bound diagnostic facts, without selected-content reads."""
    _task_id(task_id)
    require(type(include_preflight) is bool and type(max_bytes) is int
            and 1024 <= max_bytes <= MAX_BYTES, "invalid_task_limits")
    store, scope = owner_store(project)
    plan, ref = _load(store, scope, task_id)
    require(expected_plan_sha256 == ref["sha256"], "stale_plan")
    _plan_binding(project, store, scope, plan)
    context = _diagnostic_context(project, plan["request"], plan["configuration"],
                                  bindings=plan["bindings"], model=plan["model"], reasoning_effort=plan.get("reasoning_effort"), timeout=plan["timeout"],
                                  ranges=plan["ranges"], limits=plan["limits"])
    result = {"contract": "writing-assistant-task-diagnostics/1", "task_id": task_id,
              "plan_sha256": ref["sha256"], "context": context, "preflight": None,
              "validation": {"plan_binding": "verified", "selected_record_metadata": "verified",
                             "selected_content_bytes": "not_read", "external_originals": "not_read",
                             "prompt_bytes": "not_read", "parent_cas": "not_checked"},
              "model_calls": 0, "dispatch_attempts": 0}
    if include_preflight:
        remaining = max_bytes - len(canonical(result)) - 1
        require(remaining >= 2048, "output_limit")
        result["preflight"] = _diagnostic_preflight(project, context, byte_limit=min(remaining, 1024 * 1024))
    _plan_binding(project, store, scope, plan)
    require(len(canonical(result)) + 1 <= max_bytes, "output_limit")
    return result


def _drift(project, store, scope, plan):
    _plan_binding(project, store, scope, plan, write=True)
    _selection(store, scope, plan["request"], plan["bindings"], plan["ranges"],
               plan["limits"]["max_material_bytes"])
    require(_writing_relations(store, scope, plan["request"], plan["bindings"], plan["ranges"]) == plan["relations"],
            "stale_plan")
    prompt = _lookup(store, scope, plan["task_id"], "prompt")
    require(prompt is not None and digest(prompt["body"]) == plan["prompt_sha256"]
            and prompt["body"] == writing_prompt(plan["packet"]), "invalid_task_plan")
    return prompt["body"]


def execute(project, task_id, *, expected_plan_sha256, cancelled=None, artifact_resolver=None):
    """Dispatch at most once locally; never retry a reserved/unknown attempt."""
    started = monotonic()
    _task_id(task_id)
    store, scope = owner_store(project, write=True, resolver=artifact_resolver)
    initial, _ = _load(store, scope, task_id)
    require(_identity(store, scope) == initial["data_root_identity"], "authority_changed")
    with _lock(store, scope, task_id):
        plan, ref = _load(store, scope, task_id)
        require(expected_plan_sha256 == ref["sha256"], "stale_plan")
        codex.validate_options(plan["model"], plan["timeout"], cancelled, reasoning_effort=plan.get("reasoning_effort"))
        current = _view(store, scope, task_id)
        if current["status"] != "prepared":
            return _mutation_receipt(store, scope, task_id, current)
        try:
            result = _execute_locked(project, store, scope, task_id, plan, ref, cancelled)
        except (AssistantError, RecordsError, OSError) as error:
            # Early validation/authority errors must not gain telemetry effects.
            # Once reserved, preserve timing without hiding the original failure.
            _failed_timing(store, scope, task_id, ref, "execute", started, error)
            raise
        slot = "execute" if store.operation(scope, _id(scope.project_id, task_id, "intent"),
                                             include_body=False) is not None else "preflight"
        return _finish_timing(store, scope, task_id, ref, slot, started, result)


def _execute_locked(project, store, scope, task_id, plan, ref, cancelled):
    current = _view(store, scope, task_id)
    if current["status"] != "prepared":
        return _mutation_receipt(store, scope, task_id, current)
    prompt = _drift(project, store, scope, plan)
    if plan["parent"] is not None:
        require(not any(row["parent"] and row["parent"]["version_id"] == plan["parent"]["version_id"]
                        for row in store.metadata(scope)), "parent_conflict")
    context = _diagnostic_context(project, plan["request"], plan["configuration"],
                                  bindings=plan["bindings"], model=plan["model"], reasoning_effort=plan.get("reasoning_effort"), timeout=plan["timeout"],
                                  ranges=plan["ranges"], limits=plan["limits"])
    preflight = _diagnostic_preflight(project, context)
    if preflight["blocking"]:
        return _mutation_receipt(store, scope, task_id,
                                 {**current, "status": "blocked", "code": "diagnostic_blocker", "diagnostics": preflight})
    try:
        codex.qualify()
    except AssistantError as error:
        from .execution import _qualification_failure
        qualification_context = {"operation": "task-execute", "request_id": task_id,
                                 "plan_sha256": ref["sha256"], "model": plan["model"],
                                 "reasoning_effort": plan.get("reasoning_effort"), "timeout": plan["timeout"]}
        evidence = _qualification_failure(project, plan["configuration"], qualification_context, prompt, error)
        return _mutation_receipt(store, scope, task_id, {**current, "qualification": evidence, "code": error.code,
                "diagnostics": _diagnostic_failure(project, context, error.code, "qualification",
                                                     evidence_ref=evidence["observation"])})
    _drift(project, store, scope, plan)
    intent = store.save(scope, operation_id=_id(scope.project_id, task_id, "intent"),
                        body=canonical(plan["packet"]), kind="decision", title="Explicit Codex dispatch intent",
                        source={"authorship": "unknown", "origin": "Local explicit request; reservation is not execution completion"})
    if intent["status"] != "created":
        return _mutation_receipt(store, scope, task_id, _view(store, scope, task_id))
    # An interruption from this point is uncertain even if spawn never ran.
    _drift(project, store, scope, plan)
    result = _run(prompt, model=plan["model"], reasoning_effort=plan.get("reasoning_effort"), timeout=plan["timeout"], cancelled=cancelled)
    result["diagnostics_preflight"] = preflight
    facts = {key: value for key, value in result.items() if key not in {"stdout", "stderr", "output"}}
    descriptor = {"plan_sha256": ref["sha256"], "result": facts,
                  "raw": {part: {"sha256": digest(result[part]), "size": len(result[part])}
                          for part in ("stdout", "stderr", "output")}}
    descriptor_ref = _save(store, scope, task_id, "result", canonical(descriptor), related=[intent["ref"]])["ref"]
    try:
        _capture(store, scope, task_id, prompt, result, intent=intent["ref"])
    except RecordsError as error:
        if error.code == "authority_failed":
            raise
        _diagnostic_failure(project, context, error.code, "raw-capture", evidence_ref=descriptor_ref)
        raise
    _reconcile(project, store, scope, task_id, plan, ref)
    return _mutation_receipt(store, scope, task_id,
                             {**_view(store, scope, task_id), "model_calls": int(result.get("launched") is True),
                              "dispatch_attempts": 1})


def _reconcile(project, store, scope, task_id, plan, ref):
    descriptor = _lookup(store, scope, task_id, "result")
    if descriptor is None:
        return
    observed = decode(descriptor["body"])
    require(observed["plan_sha256"] == ref["sha256"], "invalid_task_evidence")
    prompt = _lookup(store, scope, task_id, "prompt")
    require(prompt is not None and digest(prompt["body"]) == plan["prompt_sha256"], "invalid_task_evidence")
    intent = store.operation(scope, _id(scope.project_id, task_id, "intent"))
    require(intent is not None and intent["body"] == canonical(plan["packet"]), "invalid_task_evidence")
    result = dict(observed["result"])
    for part in ("stdout", "stderr", "output"):
        found = store.operation(scope, _id(scope.project_id, task_id, part))
        if found is None:
            return
        require(digest(found["body"]) == observed["raw"][part]["sha256"]
                and len(found["body"]) == observed["raw"][part]["size"], "invalid_task_evidence")
        result[part] = found["body"]
    # Reconstruct an interrupted observation publication only from a complete
    # immutable descriptor and matching saved raw bytes. No provider is involved.
    receipt = _capture(store, scope, task_id, prompt["body"], result, intent=intent["ref"])
    existing = _lookup(store, scope, task_id, "receipt")
    if existing is not None:
        final = decode(existing["body"])
        for key in ("content", "provenance", "relation_record"):
            if key in final:
                store.read(scope, final[key])
        return
    if result["status"] == "completed" and len(result["output"]) > plan["limits"]["max_output_bytes"]:
        receipt = {**receipt, "status": "error", "code": "output_limit"}
    else:
        try:
            receipt = _materialize(store, scope, task_id, plan["packet"], result, receipt,
                                   parent=plan["parent"], work_id=plan["work_id"], relations=plan["relations"])
        except RecordsError as error:
            if error.code == "authority_failed":
                raise
            receipt = {**receipt, "status": "error", "code": error.code}
    model_status = result["status"]
    local_status = "completed" if "content" in receipt else "not_applicable" if model_status != "completed" else "conflict"
    state = "completed" if local_status == "completed" else "model_failed" if model_status != "completed" else "materialization_conflict"
    final = {"plan_sha256": ref["sha256"], "state": state, "model_status": model_status,
             "materialization_status": local_status, **receipt}
    if model_status != "completed" or receipt.get("code"):
        context = _diagnostic_context(project, plan["request"], plan["configuration"],
                                      bindings=plan["bindings"], model=plan["model"], reasoning_effort=plan.get("reasoning_effort"), timeout=plan["timeout"],
                                      ranges=plan["ranges"], limits=plan["limits"])
        code = receipt.get("code", model_status)
        final["diagnostics"] = _diagnostic_failure(project, context, code,
                                                   "materialization" if receipt.get("code") else "execution",
                                                   evidence_ref=receipt["observation"])
    if receipt.get("code") not in (None, "parent_conflict", "revision_scope_changed", "output_limit"):
        return  # Transient publication failure: leave recovery available.
    _save(store, scope, task_id, "receipt", canonical(final), related=[receipt["observation"]])


def reconcile(project, task_id, *, artifact_resolver=None):
    """Settle saved trustworthy bytes once; configuration changes do not resend."""
    started = monotonic()
    _task_id(task_id)
    store, scope = owner_store(project, write=True, resolver=artifact_resolver)
    initial, _ = _load(store, scope, task_id)
    require(_identity(store, scope) == initial["data_root_identity"], "authority_changed")
    with _lock(store, scope, task_id):
        plan, ref = _load(store, scope, task_id)
        require(_identity(store, scope) == plan["data_root_identity"], "authority_changed")
        current = _view(store, scope, task_id)
        recovering = current["status"] in {"model_recorded", "result_incomplete"}
        try:
            _reconcile(project, store, scope, task_id, plan, ref)
        except (AssistantError, RecordsError, OSError) as error:
            if recovering:
                _failed_timing(store, scope, task_id, ref, "reconcile", started, error)
            raise
        result = _view(store, scope, task_id)
        if recovering:
            return _finish_timing(store, scope, task_id, ref, "reconcile", started, result)
        return _mutation_receipt(store, scope, task_id, result)
