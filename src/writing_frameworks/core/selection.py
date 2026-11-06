"""Metadata selection never imports or probes optional implementations."""
from __future__ import annotations

from .contracts import fields, require

MODES = ("lotus", "none")
_UNSET = object()
PHASES = {
    "lotus": ("concept", "plan-scene", "draft", "reader-review", "continuity-review", "revise"),
    "none": ("concept", "draft", "reader-review", "continuity-review"),
}


def catalog():
    return {"schema_version": 1, "default_mode": "lotus", "implementation_probe": "not-performed",
            "modes": [{"id": "lotus", "kind": "framework", "method_version": 1, "phases": list(PHASES["lotus"])},
                      {"id": "none", "kind": "direct", "method_version": None, "phases": list(PHASES["none"])}],
            "support": "Local component contracts only; actual host integration is separately verified."}


def select(value=_UNSET):
    if value is _UNSET:
        return {"version": 1, "mode": "lotus"}
    fields(value, ("version", "mode"))
    require(type(value["version"]) is int and value["version"] == 1,
            "unsupported_version", "Unsupported writing selection version.")
    require(type(value["mode"]) is str and value["mode"] in MODES,
            "unavailable_mode", "The selected writing mode is unavailable; no fallback was applied.")
    return dict(value)


def phase_for(mode, phase):
    require(type(phase) is str and phase in PHASES[mode],
            "unsupported_phase", "This phase is unavailable for the selected writing mode.")
    return phase
