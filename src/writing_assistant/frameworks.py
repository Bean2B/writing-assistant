"""Thin bridge to pinned writing and explicit review preparation."""

from copy import deepcopy

from .core.errors import AssistantError
from .core.interface import writing_relations


def _request(request, mode):
    # Keep app-level targets separate from the pinned producer wire format.
    writing_relations(request)
    refs = [{"uri": item["uri"], "sha256": item["sha256"]} for item in request["materials"]]
    sources = [{"reference": ref, "role": original.get("role", "request-material"),
                "kind": original.get("source_kind", "unknown")}
               for ref, original in zip(refs, request["materials"])]
    value = {"schema_version": 1, "request_id": request["request_id"], "request": request["request"],
             "phase": request.get("phase", "draft"), "selection": {"version": 1, "mode": mode},
             "context": {"id": request["request_id"], "fresh": True, "frameworks_seen": []},
             "materials": refs}
    return value, sources


def prepare_lotus(request, visible):
    from writing_frameworks.provenance import prepare
    from writing_frameworks.core.contracts import ContractError
    value, sources = _request(request, "lotus")
    bodies = {item["reference"]["uri"]: item["text"].encode("utf-8") for item in visible}
    try:
        result = prepare(value, sources=sources, resolver=lambda ref: bodies[ref["uri"]])
    except ContractError as error:
        raise AssistantError(error.code) from None
    return {"instructions": result["packet"]["instructions"], "producer_request": result}


def prepare_review(request, mode, resolver):
    # The facade checks roles and freshness before any resolver content read.
    from writing_frameworks.review import prepare
    from writing_frameworks.core.contracts import ContractError
    value, sources = _request(request, mode)
    originals = {item["uri"]: item for item in request["materials"]}

    def scoped(reference):
        # Keep the public permission context (purpose/role/kind) intact.
        return resolver(deepcopy(originals[reference["uri"]]))

    try:
        result = prepare(value, requested=True, sources=sources, resolver=scoped)
    except ContractError as error:
        raise AssistantError(error.code) from None
    if "packet" not in result or result["packet"]["status"] != "ready":
        raise AssistantError("context_transition_required")
    visible = [{"reference": deepcopy(originals[item["reference"]["uri"]]), "text": item["text"]}
               for item in result["packet"]["materials"]]
    return {"materials": visible, "instructions": result["packet"]["instructions"], "producer_request": result}
