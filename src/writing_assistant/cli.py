import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core.config import change, initialize, snapshot
from .core.errors import AssistantError, require
from .core.files import read
from .core.interface import prepare, validate_request
from .core.jsonio import canonical, decode, fields


class BoundedArgumentParser(argparse.ArgumentParser):
    """Do not include user-supplied tokens in parsing diagnostics."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise AssistantError("invalid_arguments")


def parser():
    result = BoundedArgumentParser(prog="writing-assistant", allow_abbrev=False,
                                   description="AI application for Agents; model execution requires an explicit command.")
    result.add_argument("--version", action="version", version=__version__)
    sub = result.add_subparsers(dest="command", required=True)
    discovery = sub.add_parser("capabilities", help="Discover actual operations, schemas, effects, scope, limits and recovery; no provider call")
    discovery.add_argument("--project", help="Inspect only the selected project's configuration")
    selected = discovery.add_mutually_exclusive_group()
    selected.add_argument("--operation", help="Read details for one exact operation, such as 'task prepare'")
    selected.add_argument("--schema", help="Read one schema body by its catalog name")
    selected.add_argument("--detail", action="store_true", help="Read all operation details; schemas remain references")
    discovery.add_argument("--max-bytes", type=int, default=131072,
                           help="Bound complete UTF-8 JSON output including newline (1-1048576)")
    init = sub.add_parser("init", help="Create project configuration with explicit initial settings")
    init.add_argument("--project", required=True)
    init.add_argument("--data-dir", required=True)
    init.add_argument("--project-id", required=True)
    init.add_argument("--writing-mode", choices=("lotus", "none"), default="lotus")
    init.add_argument("--world-sandbox", choices=("on", "off"), default="on")
    config = sub.add_parser("config", help="Inspect or change project settings at a task boundary")
    config.add_argument("--project", required=True)
    config.add_argument("--writing-mode", choices=("lotus", "none"))
    config.add_argument("--world-sandbox", choices=("on", "off"))
    sub.add_parser("doctor", help="Inspect installed Codex capabilities without a model call")
    contract = sub.add_parser("check-request", help="Validate a versioned transport request offline")
    contract.add_argument("request_file")
    for command_name in ("prepare", "execute"):
        packet = sub.add_parser(command_name, help="Legacy ephemeral context packet; not a frozen durable task" if command_name == "prepare"
                                else "Legacy prepare-and-run operation; not execution of a frozen task plan")
        packet.add_argument("--project", required=True)
        packet.add_argument("--record-bindings", help="Explicit URI to exact Creative Records references")
        packet.add_argument("--artifacts-root", help="Explicit root for reference-backed producer originals")
        packet.add_argument("--bindings", help="Explicit producer bindings; use with --artifacts-root")
        packet.add_argument("request_file")
        if command_name == "execute":
            packet.add_argument("--timeout", type=float, default=120)
            packet.add_argument("--model", help="Explicit Codex model; omission uses CLI default, not the app's current selection")
            _reasoning_argument(packet)
    task = sub.add_parser("task", help="Prepare, inspect, diagnose, execute or reconcile one durable writing task")
    task.add_argument("--project", required=True)
    task_ops = task.add_subparsers(dest="task_command", required=True)
    task_prepare = task_ops.add_parser("prepare", help="Persist an immutable exact-input writing plan; no provider call")
    task_prepare.add_argument("request_file")
    task_prepare.add_argument("--record-bindings", help="JSON array mapping selected URIs to exact RecordStore references")
    task_prepare.add_argument("--artifacts-root", help="Explicit root for reference-backed producer originals")
    task_prepare.add_argument("--bindings", help="Explicit producer bindings; use with --artifacts-root")
    task_prepare.add_argument("--model", help="Freeze explicit model selection; omission records Codex CLI default with user config ignored")
    _reasoning_argument(task_prepare)
    task_prepare.add_argument("--timeout", type=float, default=120)
    task_prepare.add_argument("--ranges", help="JSON array of {uri,start,end}; half-open byte offsets, not continuation code-point offsets")
    task_prepare.add_argument("--limits", help="JSON object of task limits; validated by the task contract")
    for name in ("inspect", "diagnostics", "execute", "reconcile"):
        operation = task_ops.add_parser(name, help={
            "inspect": "Read bounded status, exact references and available actions; no provider call",
            "diagnostics": "Read exact task-bound diagnostic facts and optional preflight; no provider or selected-content read",
            "execute": "Execute only the inspected frozen plan; one stable attempt",
            "reconcile": "Complete local materialization from saved evidence; no provider call",
        }[name])
        operation.add_argument("task_id")
        if name == "inspect":
            operation.add_argument("--include-context", action="store_true", help="Explicitly include frozen request/material text within --max-bytes")
            operation.add_argument("--max-bytes", type=int, default=32768, help="Bound the complete UTF-8 JSON result, including newline")
        if name in {"execute", "diagnostics"}:
            operation.add_argument("--expected-plan-sha256", required=True)
        if name == "diagnostics":
            operation.add_argument("--include-preflight", action="store_true", help="Include bounded metadata-only diagnostic applicability results")
            operation.add_argument("--max-bytes", type=int, default=32768, help="Bound the complete UTF-8 JSON result, including newline")
        if name in {"execute", "reconcile"}:
            operation.add_argument("--artifacts-root", help="Explicit root for selected reference-backed originals")
            operation.add_argument("--bindings", help="Explicit producer bindings; required with --artifacts-root")
    technique = sub.add_parser("technique", help="Discover bundled versioned writing techniques; no provider call")
    technique_ops = technique.add_subparsers(dest="technique_command", required=True)
    technique_ops.add_parser("list", help="List validated bundled pack metadata and exact digests")
    technique_show = technique_ops.add_parser("show", help="Read one bundled pack and its exact digest")
    technique_show.add_argument("pack_id")
    technique_show.add_argument("--version", help="Exact pack version; omission selects the highest bundled numeric version")
    technique_suggest = technique_ops.add_parser("suggest", help="Suggest a bounded applicable set from explicit task and story tags")
    technique_suggest.add_argument("--phase", required=True)
    technique_suggest.add_argument("--task", required=True)
    technique_suggest.add_argument("--story-tag", action="append", default=[])
    technique_suggest.add_argument("--limit", type=int, default=3)
    for selected in (technique_ops.choices["list"], technique_show, technique_suggest):
        selected.add_argument("--max-bytes", type=int, default=131072,
                              help="Bound complete UTF-8 JSON output including newline (1-1048576)")
    workflow = sub.add_parser("workflow", help="Create, inspect or advance a durable writing workflow; execution stays explicit")
    workflow.add_argument("--project", required=True)
    workflow_ops = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_create = workflow_ops.add_parser("create", help="Freeze a bounded chapter workflow; no provider call")
    workflow_create.add_argument("workflow_file")
    workflow_create.add_argument("--model", help="Freeze explicit model selection for workflow tasks")
    _reasoning_argument(workflow_create)
    workflow_create.add_argument("--timeout", type=float, default=120)
    workflow_create.add_argument("--artifacts-root", help="Explicit root for selected reference-backed originals")
    workflow_create.add_argument("--bindings", help="Explicit producer bindings; required with --artifacts-root")
    for name in ("inspect", "next"):
        selected = workflow_ops.add_parser(name, help="Read exact workflow status and available actions" if name == "inspect"
                                           else "Observe completed prerequisites and prepare the next durable task; no provider call")
        selected.add_argument("workflow_id")
        selected.add_argument("--max-bytes", type=int, default=32768,
                              help="Bound complete UTF-8 JSON output including newline")
        if name == "next":
            selected.add_argument("--expected-plan-sha256", required=True)
            selected.add_argument("--expected-checkpoint-sha256", help="Require the inspected checkpoint for optimistic concurrency")
            selected.add_argument("--artifacts-root", help="Explicit root for selected reference-backed originals")
            selected.add_argument("--bindings", help="Explicit producer bindings; required with --artifacts-root")
    for name in ("update", "decide", "repair-review"):
        selected = workflow_ops.add_parser(name, help="Save explicit workflow choices with checkpoint concurrency; no provider call")
        selected.add_argument("workflow_id")
        selected.add_argument("request_file")
        selected.add_argument("--expected-plan-sha256", required=True)
        selected.add_argument("--expected-checkpoint-sha256", required=True)
        selected.add_argument("--max-bytes", type=int, default=32768)
        selected.add_argument("--artifacts-root")
        selected.add_argument("--bindings")
    state = sub.add_parser("story-state", help="Persist explicit typed story records; no model or World mutation")
    state.add_argument("--project", required=True)
    state_ops = state.add_subparsers(dest="story_state_command", required=True)
    for name in ("create", "revise", "inspect"):
        selected = state_ops.add_parser(name)
        if name != "create":
            selected.add_argument("state_id")
        if name != "inspect":
            selected.add_argument("request_file")
            selected.add_argument("--user-authorized", action="store_true", help="Acknowledge explicit user authorization for established constraints or adopted facts")
        if name == "revise":
            selected.add_argument("--expected-ref", required=True, help="JSON file containing the exact current state reference")
        if name == "inspect":
            selected.add_argument("--reference", help="JSON file containing an exact historic state reference")
        selected.add_argument("--max-bytes", type=int, default=131072)
        selected.add_argument("--artifacts-root")
        selected.add_argument("--bindings")
    _diagnostic_parser(sub)
    records = sub.add_parser("records", help="Save or read an exact Creative Records version locally")
    records.add_argument("--project", required=True)
    operation = records.add_subparsers(dest="record_command", required=True)
    save = operation.add_parser("save", help="Preserve raw bytes; no model call or adoption")
    save.add_argument("file")
    save.add_argument("--operation-id", required=True)
    save.add_argument("--title", default="")
    save.add_argument("--kind", choices=("idea", "fragment", "draft", "setting", "decision", "feedback", "prose"), default="fragment")
    save.add_argument("--parent-ref")
    save.add_argument("--work")
    save.add_argument("--authorship", choices=("user", "agent", "mixed", "unknown"), default="unknown")
    save.add_argument("--origin")
    show = operation.add_parser("read", help="Write original bytes to a new output file")
    show.add_argument("reference_file")
    show.add_argument("--output", required=True)
    operation.add_parser("list", help="List local owner-visible version metadata")
    operation.add_parser("rebuild-index", help="Rebuild the disposable index without changing originals")
    from .records.commands import extend_parser
    extend_parser(records, operation)
    world = sub.add_parser("world", help="Explicit local World Sandbox operations")
    world.add_argument("--project", required=True)
    world.add_argument("--run-id", required=True)
    world_ops = world.add_subparsers(dest="world_command", required=True)
    create = world_ops.add_parser("create", help="Create a world from an explicit external-policy configuration")
    create.add_argument("config_file")
    status = world_ops.add_parser("status", help="Owner-private progress; never a writer projection")
    status.add_argument("--replay", action="store_true")
    advance = world_ops.add_parser("advance", help="Explicitly run bounded Codex actor decisions")
    advance.add_argument("--steps", type=int, default=1,
                         help="Actor decisions in this call (1-16); separate from participant and total request limits")
    advance.add_argument("--timeout", type=float, default=120)
    advance.add_argument("--model", help="Explicit Codex model; omission uses CLI default")
    _reasoning_argument(advance)
    time = world_ops.add_parser("advance-time", help="Advance explicit narrative minutes without a model")
    time.add_argument("--target", required=True, type=int)
    time.add_argument("--event-limit", type=int, default=16)
    settle = world_ops.add_parser("settle", help="Settle only an existing durable result, including while off")
    settle.add_argument("--request-id", required=True)
    settle.add_argument("--branch", default="main")
    for name in ("projection", "resolve", "capture"):
        selected = world_ops.add_parser(name, help="Use an explicitly selected permitted projection")
        selected.add_argument("--actor", required=True)
        selected.add_argument("--branch", default="main")
        selected.add_argument("--selection")
        if name == "capture":
            selected.add_argument("--operation-id", required=True)
            selected.add_argument("--title", default="")
        else:
            selected.add_argument("--purpose", choices=("actor-projection", "world-projection"),
                                  default="actor-projection")
        if name == "projection":
            selected.add_argument("--raw", action="store_true")
        elif name == "resolve":
            selected.add_argument("reference_file")
    return result


def _reasoning_argument(command):
    from .adapters.codex import REASONING_EFFORTS
    command.add_argument("--reasoning-effort", choices=REASONING_EFFORTS,
                         help="Explicit native Codex effort; omission preserves CLI default, not the Agent's setting")


def _diagnostic_parser(sub):
    diagnostics = sub.add_parser("diagnostics", help="Explicit local diagnostic cases and bounded applicability checks")
    diagnostics.add_argument("--project", required=True)
    operations = diagnostics.add_subparsers(dest="diagnostic_command", required=True)
    capture = operations.add_parser("capture", help="Capture selected UTF-8 evidence with redaction before persistence")
    capture.add_argument("case_file", help="JSON capture metadata; see capabilities for the schema")
    capture.add_argument("--evidence", required=True, help="Explicit selected evidence file; never an automatic environment dump")
    revise = operations.add_parser("revise", help="Append an immutable case revision using exact-reference CAS")
    revise.add_argument("reference_file")
    revise.add_argument("changes_file")
    revise.add_argument("--evidence", help="Explicit selected new evidence file")
    preflight = operations.add_parser("preflight", help="Return applicable blockers, invalidation and diagnostic coverage")
    preflight.add_argument("context_file")
    query = operations.add_parser("query", help="List bounded case metadata for one component and operation")
    query.add_argument("--component", required=True)
    query.add_argument("--operation", required=True)
    for operation in (preflight, query):
        operation.add_argument("--cursor")
        operation.add_argument("--limit", type=int, default=20)
        operation.add_argument("--byte-limit", type=int, default=32768)
    show = operations.add_parser("show", help="Read one exact case revision; evidence requires an explicit option")
    show.add_argument("reference_file")
    show.add_argument("--include-evidence", action="store_true")
    show.add_argument("--byte-limit", type=int, default=32768)
    operations.add_parser("pending", help="Inspect bounded interrupted diagnostic publication")
    recover = operations.add_parser("recover", help="Recover only the selected pending publication")
    recover.add_argument("pending_id")
    recover.add_argument("--action", choices=("publish", "discard"), default="publish")
    operations.add_parser("prune", help="Explicitly prune one withdrawn case under exact latest-reference CAS").add_argument("reference_file")


def _selected_inputs(args):
    """Resolve explicit transport bindings once for legacy and durable prepare."""
    from .records.commands import json_file
    require(args.record_bindings is not None or not args.bindings, "invalid_request")
    resolver, bindings = None, []
    artifacts = _artifact_inputs(args)
    if args.record_bindings:
        from .records.application import material_resolver
        bindings = json_file(args.record_bindings)
        resolver = material_resolver(args.project, bindings, resolver=artifacts)
    return resolver, bindings, artifacts


def _artifact_inputs(args):
    require(bool(args.artifacts_root) == bool(args.bindings), "invalid_request")
    if args.bindings:
        from .records.application import artifact_resolver
        from .records.commands import json_file
        return artifact_resolver(args.artifacts_root, json_file(args.bindings))
    return None


def _task(args):
    from . import tasks
    if args.task_command == "prepare":
        from .records.commands import json_file
        request = json_file(args.request_file)
        validate_request(request)
        resolver, bindings, artifacts = _selected_inputs(args)
        return tasks.prepare(args.project, request, resolver=resolver, bindings=bindings,
                             model=args.model, reasoning_effort=args.reasoning_effort, timeout=args.timeout,
                             ranges=json_file(args.ranges) if args.ranges else (),
                             limits=json_file(args.limits) if args.limits else None,
                             artifact_resolver=artifacts)
    if args.task_command == "execute":
        return tasks.execute(args.project, args.task_id,
                             expected_plan_sha256=args.expected_plan_sha256,
                             artifact_resolver=_artifact_inputs(args))
    if args.task_command == "inspect":
        return tasks.inspect(args.project, args.task_id, include_context=args.include_context,
                             max_bytes=args.max_bytes)
    if args.task_command == "diagnostics":
        return tasks.diagnostic_context(args.project, args.task_id,
                                        expected_plan_sha256=args.expected_plan_sha256,
                                        include_preflight=args.include_preflight,
                                        max_bytes=args.max_bytes)
    return tasks.reconcile(args.project, args.task_id, artifact_resolver=_artifact_inputs(args))


def _diagnostic_reference(file):
    from .records.commands import json_file
    value = json_file(file)
    # Capture/revise results can be passed directly; no storage-ID derivation.
    if type(value) is dict and "ref" in value:
        fields(value, ("status", "ref"), ("evidence",))
        require(value["status"] in {"created", "existing", "revised", "recovered"}, "invalid_fields")
        return value["ref"]
    return value


def _technique(args):
    from .techniques import list_packs, show_pack, suggest
    require(type(args.max_bytes) is int and 0 < args.max_bytes <= 1048576, "technique_invalid_limit")
    if args.technique_command == "list":
        value = {"contract": "writing-assistant-technique-catalog/1", "packs": list_packs(), "model_calls": 0}
    elif args.technique_command == "show":
        value = {"contract": "writing-assistant-technique-view/1",
                 "pack": show_pack(args.pack_id, args.version), "model_calls": 0}
    else:
        value = suggest(args.phase, task=args.task, story_tags=args.story_tag, limit=args.limit)
    require(len(canonical(value)) + 1 <= args.max_bytes, "technique_output_limit")
    return value


def _workflow(args):
    from . import workflows
    if args.workflow_command == "create":
        from .records.commands import json_file
        return workflows.create(args.project, json_file(args.workflow_file), model=args.model,
                                reasoning_effort=args.reasoning_effort, timeout=args.timeout,
                                artifact_resolver=_artifact_inputs(args))
    if args.workflow_command == "inspect":
        return workflows.inspect(args.project, args.workflow_id, max_bytes=args.max_bytes)
    if args.workflow_command in {"update", "decide", "repair-review"}:
        from .records.commands import json_file
        operation = {"update": workflows.update, "decide": workflows.decide,
                     "repair-review": workflows.repair_review}[args.workflow_command]
        return operation(args.project, args.workflow_id, json_file(args.request_file),
                         expected_plan_sha256=args.expected_plan_sha256,
                         expected_checkpoint_sha256=args.expected_checkpoint_sha256,
                         artifact_resolver=_artifact_inputs(args), max_bytes=args.max_bytes)
    return workflows.next(args.project, args.workflow_id, expected_plan_sha256=args.expected_plan_sha256,
                          expected_checkpoint_sha256=args.expected_checkpoint_sha256,
                          artifact_resolver=_artifact_inputs(args), max_bytes=args.max_bytes)


def _story_state(args):
    from . import story_state
    from .records.commands import json_file
    resolver = _artifact_inputs(args)
    if args.story_state_command == "create":
        value = story_state.create(args.project, json_file(args.request_file),
                                  user_authorized=args.user_authorized, artifact_resolver=resolver)
    elif args.story_state_command == "revise":
        value = story_state.revise(args.project, args.state_id, json_file(args.request_file),
            expected_ref=json_file(args.expected_ref), user_authorized=args.user_authorized, artifact_resolver=resolver)
    else:
        value = story_state.inspect(args.project, args.state_id,
            reference=json_file(args.reference) if args.reference else None, artifact_resolver=resolver)
    require(type(args.max_bytes) is int and 1024 <= args.max_bytes <= 4194304, "invalid_story_state_bounds")
    require(len(canonical(value)) + 1 <= args.max_bytes, "output_limit")
    return value


def _diagnostics(args):
    from .diagnostics import owner_diagnostics
    from .records.commands import json_file
    command = args.diagnostic_command
    metadata, evidence = None, None
    if command in {"capture", "revise"}:
        metadata = json_file(args.case_file if command == "capture" else args.changes_file)
        if command == "capture":
            fields(metadata, ("case_id", "context"), ("summary", "confidence", "disposition", "diagnosis", "expires_at", "origin", "secrets"))
        else:
            fields(metadata, (), ("confidence", "disposition", "status", "diagnosis", "resolution", "summary", "expires_at", "context", "event", "secrets"))
        if args.evidence:
            file = Path(args.evidence).absolute()
            evidence = read(file.parent, file.name)
            # Decode before obtaining a writable store; selected evidence is UTF-8.
            try:
                evidence.decode("utf-8")
            except UnicodeError:
                raise AssistantError("diagnostics_evidence_utf8_required") from None
    reference = _diagnostic_reference(args.reference_file) if hasattr(args, "reference_file") else None
    context = json_file(args.context_file) if command == "preflight" else None
    store, scope = owner_diagnostics(args.project, write=command in {"capture", "revise", "recover", "prune"})
    if command == "capture":
        return store.capture(scope, evidence=evidence, **metadata)
    if command == "revise":
        if evidence is not None:
            metadata["evidence"] = evidence
        return store.revise(scope, reference, **metadata)
    if command in {"preflight", "query"}:
        options = {"cursor": args.cursor, "limit": args.limit, "byte_limit": args.byte_limit}
        if command == "preflight":
            return store.preflight(scope, context, **options)
        return store.query(scope, component=args.component, operation=args.operation, **options)
    if command == "show":
        return store.show(scope, reference, include_evidence=args.include_evidence, byte_limit=args.byte_limit)
    if command == "recover":
        return store.recover(scope, args.pending_id, action=args.action)
    if command == "prune":
        return store.prune(scope, reference)
    return store.pending(scope)


def _emit_error(payload):
    from .output_contracts import validate_error
    if not validate_error(payload):
        payload = {"status": "error", "code": "output_contract_violation"}
    print(json.dumps(payload), file=sys.stderr)
    return 2


def _operation_name(args):
    attribute = {"task": "task_command", "records": "record_command",
                 "diagnostics": "diagnostic_command", "world": "world_command",
                 "technique": "technique_command", "workflow": "workflow_command",
                 "story-state": "story_state_command"}.get(args.command)
    return args.command if attribute is None else args.command + " " + getattr(args, attribute)


def main(argv=None):
    error_context = {}
    try:
        args = parser().parse_args(argv)
        if args.command == "capabilities":
            from .capabilities import catalog
            value = catalog(project=args.project, operation=args.operation, schema=args.schema,
                            detail=args.detail, max_bytes=args.max_bytes)
        elif args.command == "task":
            value = _task(args)
        elif args.command == "technique":
            value = _technique(args)
        elif args.command == "story-state":
            value = _story_state(args)
        elif args.command == "workflow":
            from .output_contracts import OutputContractError
            workflow_identity = {"workflow_id": getattr(args, "workflow_id", None)}
            error_context = OutputContractError(_operation_name(args), workflow_identity).safe_context
            value = _workflow(args)
        elif args.command == "diagnostics":
            value = _diagnostics(args)
        elif args.command == "init":
            value = initialize(args.project, args.data_dir, args.project_id,
                               writing_mode=args.writing_mode, world_sandbox=args.world_sandbox == "on")
        elif args.command == "config":
            if args.writing_mode is None and args.world_sandbox is None:
                value = snapshot(args.project)
            else:
                value = change(args.project, writing_mode=args.writing_mode,
                               world_sandbox=None if args.world_sandbox is None else args.world_sandbox == "on")
        elif args.command == "doctor":
            from .adapters.codex import doctor
            value = doctor()
        elif args.command in {"records", "world"}:
            from .records.commands import execute, RawOutput
            if args.command == "world":
                try:
                    from .world.commands import execute
                except ImportError:
                    raise AssistantError("world_component_unavailable") from None
            value = execute(args)
            if isinstance(value, RawOutput):
                from .output_contracts import validate_raw_output
                validate_raw_output(_operation_name(args), value.body,
                                    requested=getattr(args, "raw", False) or _operation_name(args) == "world resolve")
                sys.stdout.buffer.write(value.body)
                return 0
        else:
            file = Path(args.request_file).absolute()
            request = decode(read(file.parent, file.name))
            if args.command == "check-request":
                validate_request(request)
                value = {"status": "valid", "executed": False}
            else:
                validate_request(request)
                resolver, record_bindings, _artifacts = _selected_inputs(args)
                if args.command == "execute":
                    from .execution import writing
                    value = writing(args.project, request, resolver=resolver,
                                    bindings=record_bindings, model=args.model, timeout=args.timeout,
                                    reasoning_effort=args.reasoning_effort,
                                    artifact_resolver=_artifacts)
                else:
                    value = prepare(request, snapshot(args.project), resolver=resolver)
        from .output_contracts import validate_output
        validate_output(_operation_name(args), value, include_evidence=args.include_evidence
                        if args.command == "diagnostics" and args.diagnostic_command == "show" else None,
                        requested_raw=getattr(args, "raw", False) or _operation_name(args) == "world resolve",
                        mutation=(args.writing_mode is not None or args.world_sandbox is not None)
                        if args.command == "config" else None)
        # The continuation owner budgets compact UTF-8 JSON plus one newline.
        # Emit that same representation so transport whitespace cannot exceed it.
        sys.stdout.buffer.write(canonical(value) + b"\n")
        if args.command == "workflow" and args.workflow_command == "next" and value["status"] == "blocked":
            return _emit_error({"status": "error", "code": value.get("code", "workflow_task_blocked"),
                                "operation": "workflow next", "workflow_id": value["workflow_id"],
                                "effect_status": "unknown"})
        if (args.command == "execute"
                or (args.command == "task" and args.task_command in {"execute", "reconcile"})
                or (args.command == "world" and args.world_command == "advance")):
            if value["status"] not in {"completed", "paused"}:
                return _emit_error({"status": "error", "code": value.get("code", value["status"])})
        return 0
    except AssistantError as error:
        code = error.code
        from .output_contracts import OutputContractError
        if isinstance(error, OutputContractError):
            error_context = error.safe_context
    except FileExistsError:
        code = "already_exists"
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError) as error:
        from .records.core import RecordsError
        from .records.continuation import ContextBudgetError
        if isinstance(error, ContextBudgetError):
            return _emit_error({"status": "error", "code": error.code,
                                "required_bytes": error.required_bytes, "allowed_bytes": error.allowed_bytes})
        code = error.code if isinstance(error, RecordsError) else "local_input_error"
    return _emit_error({"status": "error", "code": code, **error_context})
