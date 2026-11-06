"""Machine-readable discovery over the actual parser and shipped schemas.

This module describes effects; it does not implement another request validator
or invoke a provider. Command argument truth stays in cli.parser, schema bytes
stay in their shipped files, and runtime semantics stay in the owning modules.
"""

import argparse
from importlib import metadata
from pathlib import Path

from . import __version__
from .core.errors import AssistantError, require
from .core.files import read
from .core.jsonio import canonical, decode


SCHEMAS = {
    "configuration": "config-v1.schema.json",
    "request": "request-v1.schema.json",
    "record": "creative-records-v1.schema.json",
    "continuation": "creative-continuation-v1.schema.json",
    "diagnostic-capture": "diagnostic-capture-v1.schema.json",
    "diagnostic-revision": "diagnostic-revision-v1.schema.json",
    "core-results": "core-results-v1.schema.json",
    "technique-pack": "technique-pack-v1.schema.json",
    "writing-workflow": "writing-workflow-v1.schema.json",
    "story-state": "story-state-v1.schema.json",
    "story-context": "story-context-v1.schema.json",
    "review-decision": "review-decision-v1.schema.json",
}


def _schema(name):
    filename = SCHEMAS[name]
    source = Path(__file__).resolve().parents[2] / "schemas" / filename
    if source.is_file():
        return decode(read(source.parent, source.name))
    # A wheel installs non-package assets under its data scheme. Distribution
    # RECORD locates that scheme for venv, user and relocated installations.
    try:
        distribution = metadata.distribution("writing-assistant")
        suffix = "share/writing-assistant/schemas/" + filename
        for entry in distribution.files or ():
            if entry.as_posix().endswith(suffix):
                path = Path(distribution.locate_file(entry)).absolute()
                return decode(read(path.parent, path.name))
    except metadata.PackageNotFoundError:
        pass
    raise AssistantError("capability_schema_unavailable")


def _arguments(command):
    result = []
    for action in command._actions:
        if isinstance(action, (argparse._SubParsersAction, argparse._HelpAction, argparse._VersionAction)):
            continue
        item = {"name": action.dest, "options": list(action.option_strings),
                "required": action.required,
                "takes_value": action.nargs != 0,
                "type": "boolean" if isinstance(action, argparse._StoreTrueAction)
                else {int: "integer", float: "number"}.get(action.type, "string")}
        if action.help and action.help != argparse.SUPPRESS:
            item["description"] = action.help
        if action.choices is not None:
            item["choices"] = list(action.choices)
        if action.default is not None and action.default != argparse.SUPPRESS:
            item["default"] = action.default
        result.append(item)
    return result


def _commands(command, path=(), inherited=()):
    arguments = (*inherited, *_arguments(command))
    children = next((a for a in command._actions if isinstance(a, argparse._SubParsersAction)), None)
    if children:
        for name, child in children.choices.items():
            yield from _commands(child, (*path, name), arguments)
    else:
        yield path, list(arguments)


def _operation(path, arguments):
    from .output_contracts import output_schema
    name = " ".join(path)
    group = path[0]
    leaf = path[-1]
    provider = name in {"execute", "task execute", "world advance"}
    probing = name == "doctor" or provider
    record_writes = {"save", "rebuild-index", "bind-record-routes", "bookmark", "import-writer", "import-actor"}
    world_writes = {"create", "advance", "advance-time", "settle", "capture"}
    diagnostic_writes = {"capture", "revise", "recover", "prune"}
    writes = (name in {"init", "execute", "task prepare", "task execute", "task reconcile", "workflow create", "workflow next", "workflow update", "workflow decide", "workflow repair-review", "story-state create", "story-state revise"}
              or (group == "records" and leaf in record_writes)
              or (group == "world" and leaf in world_writes)
              or (group == "diagnostics" and leaf in diagnostic_writes))
    effects = {"model_dispatch": "explicit" if provider else "none",
               "subprocess": "codex-capability-probes-and-explicit-dispatch" if provider
               else "codex-capability-probes-only" if probing else "none",
               "local_write": "conditional-configuration-change" if name == "config"
               else "selected-output-file" if name == "records read"
               else "explicit-selected-operation" if writes else "none",
               "adoption": "never", "automatic_retry": False}
    scope = "explicit initialized project and owner data-root authority"
    if name in {"capabilities", "doctor", "check-request", "init"}:
        scope = {"capabilities": "application metadata; optional selected project configuration only",
                 "doctor": "installed Codex capability probes; no model call",
                 "check-request": "explicit request JSON only",
                 "init": "explicit project and separate data directory"}[name]
    if group == "technique":
        scope = "bounded bundled data-only technique packs; no project or manuscript reads"
    limits = ["Each selected input file has a bounded read; runtime semantics validate before affected effects."]
    inputs, outputs = [], "json"
    recovery = ["inspect-error-code", "correct-selected-input-or-authority"]
    configurations = {"writing_modes": ["lotus", "none"], "world_sandbox": [True, False]}
    if name in {"prepare", "execute", "task prepare", "check-request"}:
        inputs.append("request")
        limits += ["At most 32 material references and 1048576 UTF-8 request bytes.",
                   "At most 4194304 resolved material bytes; only explicitly bound exact versions."]
        limits.append("Techniques require explicit exact pack versions, discovery digests and technique IDs; omitted or empty selection loads none.")
    if group == "technique":
        outputs = {"list": "writing-assistant-technique-catalog/1", "show": "writing-assistant-technique-view/1",
                   "suggest": "writing-assistant-technique-suggestions/1"}[leaf]
        limits += ["At most 32 bundled packs, with at most 16 techniques and 65536 source bytes per pack.",
                   "Complete UTF-8 JSON including newline is bounded by --max-bytes; maximum 1048576.",
                   "Show without --version chooses the highest bundled numeric version; requests still require the exact returned version and digest.",
                   "Pack text supplies task guidance only; it grants no material authority, adoption or World Sandbox facts."]
        if leaf == "suggest":
            limits += ["Suggestions use declared phase/task and explicit tags only, return at most three exact selections and apply none.",
                       "A zero limit or an empty accepted selection remains valid; suggestions do not enlarge a workflow prompt."]
        recovery = ["technique list", "technique show", "select-exact-pack-version-digest-and-technique-ids"]
    if group == "workflow":
        outputs = "writing-assistant-workflow/1"
        inputs = ["writing-workflow"] if leaf == "create" else []
        limits += ["One frozen chapter workflow with exact plan and checkpoint references; no model dispatch or automatic adoption.",
                   "At most 20 chapters per workflow, with explicit actual start_chapter and last chapter number at most 20000; selected policy determines the bounded phase sequence.",
                   "Only a task with completed model and local materialization states and verified exact output may satisfy a dependency.",
                   "Failed, blocked, uncertain or conflicting prerequisites stop progression; preserve the existing task identity.",
                   "Next requires expected_plan_sha256; optional expected_checkpoint_sha256 checks the inspected checkpoint.",
                   "Inspect and next bound complete UTF-8 JSON including newline with --max-bytes (1024-4194304, default 32768); output references may use an explicit compact checkpoint view.",
                   "A blocked next emits its status view on stdout and exit 2 with a payload-free JSON error on stderr; inspect remains a successful status query."]
        limits += ["New reviews require structured evidence companions; malformed or unavailable feedback is never a pass.",
                   "Only unresolved confirmed-contradiction material claims trigger the configured advisory, hold or at-most-one revision action; preferences and uncertainty do not force rewrites.",
                   "Update and decide require exact plan and checkpoint digests and retain choices in immutable records; prepared task inputs remain frozen.",
                   "Repair-review validates supplied corrected structure against the same exact originals and preserves the original review; it does not redispatch.",
                   "Context reads only supplied state, earlier prose and application-owned recent chapters; exclusions and purpose changes remain inspectable."]
        recovery = ["workflow inspect", "task inspect", "task reconcile", "workflow next"]
    if group == "story-state":
        outputs = "writing-assistant-story-state/1"
        inputs = ["story-state"] if leaf != "inspect" else []
        limits += ["Typed state uses exact RecordStore evidence and immutable revisions; generated content remains proposal.",
                   "Established constraints, adopted facts and their replacement require explicit user authorization; no World Sandbox mutation occurs.",
                   "Inspect can read an exact historical state; selection refuses stale current-state references and missing evidence."]
        recovery = ["story-state inspect", "read-returned-exact-record-reference"]
    if name.startswith("task "):
        limits += ["One stable local attempt per task ID; inspect/reconcile target that task's immutable records.",
                   "Task ranges use half-open byte offsets; do not substitute continuation code-point offsets."]
        recovery = ["task inspect", "read-returned-exact-record-reference", "task reconcile"]
    if name in {"task prepare", "task execute", "task reconcile"}:
        limits.append("Mutation results fit 32768 UTF-8 JSON bytes including newline; oversized views return a compact receipt with exact detail references and explicit omitted fields.")
    if name == "task execute":
        limits += ["expected_plan_sha256 is required; changed configuration, sources, policy or authority refuse dispatch.",
                   "Uncertain/reserved work is never resent; completed duplicates return the saved outcome."]
    if name == "task inspect":
        limits.append("Only uncertain/reserved work without a saved result includes local_runtime lock observation and reservation age; backend status stays unknown, not model progress or retry authority.")
    if name == "task diagnostics":
        outputs = "writing-assistant-task-diagnostics/1"
        limits += ["Requires expected_plan_sha256; authenticates live plan/configuration/policy/authority and selected record metadata.",
                   "Returns the execute hook's exact diagnostic context; copy it unchanged except for the observed category when capturing a case.",
                   "No selected content, external original or prompt bytes are read; parent CAS is not checked. Consult returned validation.",
                   "Optional preflight returns bounded diagnostic metadata; this operation grants no dispatch or retry authority."]
        limits.append("Changed routing/CA metadata invalidates diagnostic reuse; child_routing_proof=unknown prevents automatic reuse.")
        recovery = ["task inspect", "diagnostics capture", "diagnostics revise", "task diagnostics"]
    if name in {"prepare", "execute"}:
        limits.append("Legacy operation: ephemeral preparation or immediate prepare-and-run; no frozen-plan execution binding.")
    if group == "records":
        if leaf in {"read", "show"}:
            inputs.append("record#/properties/related/items")
        if leaf in {"read", "show"}:
            limits.append("An explicit exact-version read may return the complete selected body, bounded by RecordStore BODY_LIMIT.")
        if leaf == "show":
            outputs = "json-or-explicit-original-bytes-with---raw"
        if leaf in {"recent", "search"}:
            limits += ["Paginated complete metadata items; max_bytes bounds compact UTF-8 JSON including newline (default 32768, maximum 16777216). Search reads stored bodies locally.",
                       "The half-open returned-item range and next_cursor identify continuation; follow returned next_cursor unchanged until null. Byte limits may shorten a page below limit.",
                       "An oversized first item returns context_budget_exceeded with safe required_bytes/allowed_bytes; increase max_bytes at the same cursor. No metadata is trimmed and no item is skipped."]
        if leaf in {"list", "search"}:
            limits += ["CLI traversal is incremental in version-ID order; scan_limit bounds source versions checked per call (default 100, maximum 2000). An empty match page can still have a next_cursor.",
                       "total is null; scan.scanned and scan.complete describe this traversal, not a global newest/complete content result. Follow next_cursor even when items/versions is empty."]
        if leaf == "list":
            limits.append("CLI metadata pages use limit/cursor/max_bytes; Python legacy complete-list return remains readable. No original body is read for a metadata page.")
        if leaf == "history":
            limits.append("CLI version-chain pages use limit/cursor/max_bytes; complete bounded metadata topology is validated before identifying total/latest_stored, and only returned-page bodies are verified. Python legacy complete-history shape remains readable.")
        if leaf in {"list", "search", "recent", "history"}:
            limits.append("Version namespace enumeration has a hard cap of 10000 entries; scan_limit_exceeded refuses oversized namespaces. Existing authority, source-integrity and I/O/deadline checks still apply.")
        if leaf == "recent":
            limits.append("Latest ordering and total require complete metadata traversal within the namespace/I/O bounds; page-byte limits alone do not limit scan work.")
        if leaf in {"context", "bookmark", "read-bookmark", "bookmarks"}:
            inputs.append("continuation")
            limits.append("Continuation ranges use unicode_code_points_utf8_including_bom; context enforces max_bytes.")
        if leaf == "bookmarks":
            scope = "full owner of the explicit initialized project and data-root authority; no record subset"
            limits += ["Newest 1-200 saved bookmark metadata entries; complete UTF-8 JSON including newline is bounded by max_bytes.",
                       "All owner bookmark sources are checked within existing I/O/deadline bounds; failed or corrupt scans return no partial latest selection.",
                       "Returns exact bookmark/selected references, save time, operation ID, stop and baseline; no prose or question text."]
        if leaf == "context":
            limits += ["Select exactly one of --bookmark FILE or the full-owner --latest-bookmark convenience entrypoint.",
                       "Latest means newest saved bookmark, not newest record version; returns that exact bookmark and selected reference.",
                       "Existing baseline, source integrity and total serialized UTF-8 byte checks apply; no generation or adoption."]
    if group == "world":
        limits.append("Only the selected run/actor/projection; supported predecessor runs are read-only.")
        if leaf in {"create", "advance", "advance-time", "capture"}:
            configurations["world_sandbox"] = [True]
        if leaf == "advance":
            limits.append("1-16 actor decisions per call, plus run participant/total request limits.")
        if leaf in {"projection", "resolve"}:
            outputs = "json-or-explicit-projection-bytes" if leaf == "projection" else "projection-bytes"
    if group == "diagnostics":
        inputs += ["diagnostic-capture"] if leaf == "capture" else ["diagnostic-revision"] if leaf == "revise" else []
        if leaf == "preflight":
            inputs.append("diagnostic-capture#/$defs/context")
        limits += ["Explicit selected UTF-8 evidence only; redact before persistence.",
                   "Metadata-only by default; show --include-evidence explicitly reads bounded retained evidence.",
                   "Confirmed applicable open blockers affect their operation only; advisory cases do not authorize retries.",
                   "Optional store damage reports reduced coverage; authority and data-integrity checks remain mandatory."]
        recovery = ["diagnostics show", "diagnostics preflight", "diagnostics pending", "diagnostics recover"]
    result = {"operation": name, "command": "writing-assistant " + name,
            "arguments": arguments, "input_schemas": inputs, "output": outputs,
            "output_schema": output_schema(name),
            "output_validation": "original-bytes" if name == "world resolve" else
                                 "json-fields-or-original-bytes" if name in {"records show", "world projection"} else
                                 "core-fields" if output_schema(name) is not None else "not-covered",
            "effects": effects, "scope": scope, "limits": limits,
            "request_kinds": ["writing"] if name in {"execute", "task prepare", "task execute"}
            else ["writing", "world-action"] if name in {"prepare", "check-request"} else [],
            "configuration_support": configurations,
            "error_contract": "payload-free-json-stderr/1", "recovery": recovery}
    if name in {"records show", "world projection"}:
        result["output_variants"] = [
            {"when": "default", "transport": "json", "schema": output_schema(name), "validation": "core-fields"},
            {"when": "--raw", "transport": "bytes", "schema": None, "validation": "bounded-original-bytes"}]
    if name == "world resolve":
        result["output_variants"] = [{"when": "world resolve", "transport": "bytes", "schema": None,
                                      "validation": "bounded-original-bytes"}]
    if name == "diagnostics show":
        result["output_variants"] = [
            {"when": "default", "transport": "json", "schema": "core-results#/$defs/diagnosticMetadata", "validation": "core-fields"},
            {"when": "--include-evidence", "transport": "json", "schema": "core-results#/$defs/diagnosticExplicitEvidence", "validation": "core-fields"}]
    return result


def _detail_catalog():
    from dataclasses import asdict
    from .cli import parser
    from .core.interface import DIRECT_PHASES, WRITING_PHASES
    from .tasks import CONTRACT as TASK_CONTRACT, DEFAULT_LIMITS
    from .workflows import CONTRACT as WORKFLOW_CONTRACT, DEFAULT_LIMITS as WORKFLOW_LIMITS, MAX_CHAPTERS
    from .techniques import PACK_SCHEMA, SELECTION_SCHEMA, MAX_PACKS, MAX_PACK_BYTES, MAX_SELECTED_PACKS, MAX_SELECTED_TECHNIQUES
    from .diagnostics import CONTRACT as DIAGNOSTIC_CONTRACT, DiagnosticLimits
    from .records.core import BODY_LIMIT
    schemas = _schema_index()
    request_schema, record_schema = _schema("request"), _schema("record")
    result = {"schema_version": "writing-assistant-capabilities/1", "application_version": __version__,
              "text_operations": ["--help", "--version"],
              "operations": [_operation(path, args) for path, args in _commands(parser())],
              "schemas": schemas,
              "contracts": {"task": TASK_CONTRACT, "diagnostics": DIAGNOSTIC_CONTRACT,
                            "workflow": WORKFLOW_CONTRACT, "technique_pack": PACK_SCHEMA, "technique_selection": SELECTION_SCHEMA},
              "default_limits": {"task": DEFAULT_LIMITS, "diagnostics": asdict(DiagnosticLimits()),
                                 "record_body_bytes": BODY_LIMIT, "workflow": {**WORKFLOW_LIMITS, "max_chapters": MAX_CHAPTERS},
                                 "techniques": {"bundled_pack_versions": MAX_PACKS, "pack_bytes": MAX_PACK_BYTES,
                                                "selected_packs": MAX_SELECTED_PACKS, "selected_techniques": MAX_SELECTED_TECHNIQUES}},
              "task_options": {"limits": {"type": "object", "additionalProperties": False,
                                           "required": list(DEFAULT_LIMITS),
                                           "properties": {key: {"type": "integer", "minimum": 1, "maximum": value, "default": value}
                                                          for key, value in DEFAULT_LIMITS.items()}},
                               "ranges": {"type": "array", "maxItems": request_schema["properties"]["materials"]["maxItems"],
                                          "offset_unit": "bytes", "interval": "half-open", "encoding": "selected bytes must decode as UTF-8",
                                          "items": {"type": "object", "additionalProperties": False,
                                                    "required": ["uri", "start", "end"],
                                                    "properties": {"uri": {"type": "string"}, "start": {"type": "integer", "minimum": 0},
                                                                   "end": {"type": "integer", "minimum": 0}}}},
                               "bindings": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["uri", "ref"], "properties": {"uri": {"type": "string"},
                                                     "ref": record_schema["properties"]["related"]["items"]}},
                                            "selection": "exact returned RecordStore reference for every material URI"}},
              "writing_support": {"lotus": list(WRITING_PHASES),
                                  "none": list(DIRECT_PHASES),
                                  "world_setting_independent": True,
                                  "request_validation": "writing_assistant.core.interface.validate_request",
                                  "relation_validation": "writing_assistant.core.interface.writing_relations"},
              "errors": {"transport": {"exit_code": 2, "stream": "stderr", "fields": ["status", "code"],
                                        "output_schema": "core-results#/$defs/cliError",
                                        "optional_fields_by_code": {"context_budget_exceeded": ["required_bytes", "allowed_bytes"],
                                            "output_contract_violation": ["operation", "effect_status", "task_id", "attempt_id", "workflow_id", "plan_sha256", "checkpoint_sha256", "case_id", "pending_id", "project_id", "request_id", "run_id", "configuration_sha256", "references"],
                                            "workflow-errors": ["operation", "effect_status", "workflow_id"]},
                                        "private_arguments_echoed": False},
                         "recovery": {
                             "invalid_arguments": "Use this catalog's exact arguments or command --help; do not use abbreviated options.",
                             "invalid_fields": "Use only the supported schema fields; validation performs no model dispatch.",
                             "capabilities_output_limit": "Select one operation or schema, or increase --max-bytes within its maximum.",
                             "context_budget_exceeded": "Increase --max-bytes using required_bytes/allowed_bytes; for records pages retain the same cursor. Explicit context selections may instead use a narrower authorized range.",
                             "unsupported_interface_version": "Use writing-assistant-request/1.",
                             "unsupported_phase": "Select a phase supported by the active writing mode.",
                             "feedback_target_required": "Bind feedback to the exact selected current-draft uri and sha256.",
                             "feedback_target_mismatch": "Select applicable feedback; no automatic retargeting.",
                             "changed_technique_pack": "Read the selected bundled pack again and inspect its exact version and digest before preparing a new task.",
                             "technique_output_limit": "Select one pack or increase --max-bytes within its maximum; no pack data is truncated.",
                             "workflow_conflict": "Preserve the existing workflow and inspect its frozen plan; do not replace its identity with changed input.",
                             "stale_workflow": "Inspect the workflow and its current plan/checkpoint digests before advancing it.",
                             "stale_workflow_checkpoint": "Inspect the workflow's current checkpoint before another next operation; no replacement task is authorized.",
                             "workflow_task_blocked": "Preserve the current task identity and inspect its saved status/evidence; dependent stages cannot proceed.",
                             "workflow_review_hold": "Read exact review_decision references and preserve feedback; use workflow decide for explicit choices before next.",
                             "review_decisions_missing": "Preserve the original completed review and supply a grounded structured companion with workflow repair-review; do not repeat model execution.",
                             "invalid_review_output": "Inspect the original review and exact selected evidence; repair only supported structure through workflow repair-review without redispatch.",
                             "stale_story_state": "Inspect the latest state and explicitly update the workflow context for successor tasks; existing tasks remain frozen.",
                             "stale_plan": "Inspect the original task and exact plan; do not dispatch changed inputs.",
                             "task_conflict": "Preserve the original task; its identity cannot be replaced with different inputs.",
                             "parent_conflict": "Inspect exact draft history and saved output; never regenerate to resolve a local CAS conflict.",
                             "uncertain_request": "Inspect and reconcile saved evidence; do not resend under another ID.",
                             "busy": "Inspect the existing operation; never delete a live lock.",
                             "local_input_error": "Check selected regular files and physical paths; private details are omitted.",
                             "output_contract_violation": "Preserve returned safe operation identity and exact references; inspect existing effects before any further action. No resend is authorized."}},
              "authority": {"operator": "Agent", "beneficiary": "user", "adoption": "user decision only",
                            "material_text_grants_authority": False,
                            "provider_limits": "Local process/time/byte bounds do not prove backend termination, remote exactly-once or hard remote cost limits."}}
    return result


def _schema_index():
    return {name: {"path": "schemas/" + filename} for name, filename in SCHEMAS.items()}


def catalog(*, project=None, operation=None, schema=None, detail=False, max_bytes=131072):
    """Return bounded discovery; schema bodies and operation details are opt-in."""
    from .cli import parser
    from .core.interface import DIRECT_PHASES, WRITING_PHASES

    require(type(max_bytes) is int and 0 < max_bytes <= 1048576, "capabilities_invalid_limit")
    require(type(detail) is bool and sum((operation is not None, schema is not None, detail)) <= 1,
            "invalid_capability_selection")
    require(operation is None or type(operation) is str, "invalid_capability_selection")
    require(schema is None or type(schema) is str, "invalid_capability_selection")
    if schema is not None:
        require(schema in SCHEMAS, "unknown_capability_schema")
        result = {"schema_version": "writing-assistant-capabilities/1", "application_version": __version__,
                  "view": "schema", "schemas": {schema: {**_schema_index()[schema], "schema": _schema(schema)}}}
    elif detail or operation is not None:
        result = _detail_catalog()
        if operation is not None:
            selected = [item for item in result["operations"] if item["operation"] == operation]
            require(bool(selected), "unknown_capability_operation")
            result["operations"] = selected
            if operation != "task prepare":
                result.pop("task_options")
        result["view"] = "operation" if operation is not None else "detail"
    else:
        summaries = []
        for path, args in _commands(parser()):
            item = _operation(path, args)
            summaries.append({"operation": item["operation"],
                              "model_dispatch": item["effects"]["model_dispatch"],
                              "local_write": item["effects"]["local_write"]})
        result = {"schema_version": "writing-assistant-capabilities/1", "application_version": __version__,
                  "view": "overview", "operations": summaries, "schemas": _schema_index(),
                  "writing_support": {"lotus": list(WRITING_PHASES), "none": list(DIRECT_PHASES),
                                      "world_setting_independent": True},
                  "discovery": {"operation": "capabilities --operation 'task prepare'",
                                "schema": "capabilities --schema request",
                                "detail": "capabilities --detail",
                                "output_bound": "--max-bytes bounds complete UTF-8 JSON including newline; maximum 1048576"},
                  "authority": {"operator": "Agent", "beneficiary": "user", "adoption": "user decision only"}}
    if project is not None:
        from .core.config import snapshot
        configuration = snapshot(project)
        # Do not disclose the configured private data path in ordinary discovery.
        effective = configuration["effective"]
        result["project"] = {"project_id": effective["project_id"], "configuration_sha256": configuration["sha256"],
                             "writing_mode": effective["writing_mode"], "world_sandbox": effective["world_sandbox"],
                             "codex_adapter": effective["codex_adapter"]}
    require(len(canonical(result)) + 1 <= max_bytes, "capabilities_output_limit")
    return result
