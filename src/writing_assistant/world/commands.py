"""Explicit CLI operations for configured local world runs."""

from ..core.errors import AssistantError
from ..core.jsonio import decode
from ..records.commands import RawOutput, json_file
from .service import open_run


def execute(args):
    if args.world_command == "advance":
        from ..execution import world_client
        evidence = []
        try:
            decide = world_client(args.project, args.run_id, model=args.model,
                                  reasoning_effort=getattr(args, "reasoning_effort", None),
                                  timeout=args.timeout, evidence=evidence)
            with open_run(args.project, args.run_id) as session:
                result = session.advance(decision_client=decide, steps=args.steps)
                return {**result, "execution_evidence": evidence}
        except AssistantError as error:
            if not evidence:
                raise
            return {"status": "error", "code": error.code, "execution_evidence": evidence,
                    "run_id": args.run_id}
    create = args.world_command == "create"
    with open_run(args.project, args.run_id, create=create,
                  config=json_file(args.config_file) if create else None) as session:
        if create or args.world_command == "status":
            return session.status(replay=not create and args.replay)
        if args.world_command == "advance-time":
            return session.advance_time(target=args.target, event_limit=args.event_limit)
        if args.world_command == "settle":
            return session.settle(request_id=args.request_id, branch_id=args.branch)
        selection = json_file(args.selection) if args.selection else None
        if args.world_command == "capture":
            return session.capture(actor_id=args.actor, branch_id=args.branch,
                                   selection=selection, operation_id=args.operation_id, title=args.title)
        if args.world_command == "resolve":
            body = session.resolve(json_file(args.reference_file), actor_id=args.actor,
                                   branch_id=args.branch, purpose=args.purpose, selection=selection)
            return RawOutput(body)
        packet = session.projection(actor_id=args.actor, branch_id=args.branch,
                                    purpose=args.purpose, selection=selection)
        return RawOutput(packet["body"]) if args.raw else {"reference": packet["reference"],
                                                            "body": decode(packet["body"])}
