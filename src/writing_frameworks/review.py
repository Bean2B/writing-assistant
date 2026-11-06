"""Explicit, narrowly scoped prose review using the existing producer formats."""
from . import provenance
from .core.contracts import fields, require
from .core.selection import select

PHASES = ("reader-review", "continuity-review")
ROLES = {
    "reader-review": frozenset(("current-draft", "prior-prose")),
    "continuity-review": frozenset(("current-draft", "prior-prose", "scene-projection", "request-material")),
}


def prepare(request=None, *, requested=False, sources=None, resolver=None):
    """Prepare an explicitly requested review; otherwise touch no materials.

    Returns the existing provenance prepared request or new-context-required
    response, or None when review was not requested. This never dispatches a
    model, changes content, records adoption or authenticates host independence.
    """
    require(type(requested) is bool, "invalid_request", "Review choice must be an explicit boolean.")
    if not requested:
        return None
    fields(request, ("schema_version", "request_id", "request", "phase", "context", "materials", "selection"))
    select(request["selection"])
    phase = request["phase"]
    require(type(phase) is str and phase in PHASES,
            "unsupported_phase", "Explicit prose evaluation requires reader-review or continuity-review.")
    selected = provenance._sources(sources, request["materials"], phase)
    require(all(row["role"] in ROLES[phase] for row in selected),
            "invalid_relation", "Independent review materials exceed the selected perspective.")
    return provenance.prepare(request, sources=selected, resolver=resolver)
