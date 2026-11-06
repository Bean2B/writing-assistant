"""Lotus instruction adapter, loaded only after explicit mode/phase selection."""
from importlib.resources import files

PHASE_RULES = {
    "concept": "Develop initial story concept candidates from the supplied goals and selected ideas. Explore premise, characters, pressures, world and plot possibilities without requiring an existing scene or draft. Keep proposed details as candidates; do not adopt content or establish world facts.",
    "plan-scene": "Prepare current scene conditions, visible information and purpose. Keep possible outcomes open.",
    "draft": "Write from the selected current-scene materials and exact prior prose. Return the actual draft.",
    "reader-review": "Form an independent reading standard before reading the permitted prose. Cite actual textual experience; do not receive hidden author answers.",
    "continuity-review": "Review permitted inputs and actual prose for knowledge, costs, space, time and consequences. Distinguish observation, intention and inference.",
    "revise": "Address the explicitly selected feedback against its exact draft version. Preserve unaffected accepted text and retain the earlier original.",
}


def instructions(phase):
    return files(__package__).joinpath("instructions.md").read_text(encoding="utf-8") + "\n" + PHASE_RULES[phase]
