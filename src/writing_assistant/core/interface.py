"""Transport contract only; record/version ownership stays with Creative Records."""

import re
from copy import deepcopy

from .errors import require
from .config import validate as validate_config
from .jsonio import canonical, digest, fields

IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
WRITING_PHASES = ("concept", "draft", "plan-scene", "reader-review", "continuity-review", "revise")
DIRECT_PHASES = ("concept", "draft", "reader-review", "continuity-review", "revise")


def _exact_reference(value):
    fields(value, ("uri", "sha256"))
    require(type(value["uri"]) is str and 0 < len(value["uri"]) <= 2048, "invalid_reference")
    require(type(value["sha256"]) is str and HASH.fullmatch(value["sha256"]), "invalid_reference")
    return dict(value)


def _reference(material):
    return {"uri": material["uri"], "sha256": material["sha256"]}


def validate_request(value):
    fields(value, ("schema_version", "request_id", "project_id", "kind", "request", "materials"), ("phase", "techniques"))
    require(value["schema_version"] == "writing-assistant-request/1", "unsupported_interface_version")
    for key in ("request_id", "project_id"):
        require(type(value[key]) is str and IDENTIFIER.fullmatch(value[key]), "invalid_identifier")
    require(value["kind"] in ("writing", "world-action"), "unsupported_request_kind")
    require(value.get("phase", "draft") in WRITING_PHASES, "unsupported_phase")
    require(value["kind"] == "writing" or "phase" not in value, "unsupported_phase")
    if "techniques" in value:
        require(value["kind"] == "writing", "unsupported_techniques")
        from writing_assistant.techniques import validate_selection
        validate_selection(value["techniques"])
    require(type(value["request"]) is str and len(value["request"].encode("utf-8")) <= 1024 * 1024, "input_limit")
    refs = value["materials"]
    require(type(refs) is list and len(refs) <= 32, "input_limit")
    for ref in refs:
        fields(ref, ("uri", "sha256", "purpose"), ("role", "source_kind", "feedback_target"))
        _exact_reference(_reference(ref))
        require(ref["purpose"] in ("current-writing", "world-projection", "actor-projection"), "invalid_purpose")
        require(ref.get("role", "request-material") in ("request-material", "prior-prose", "current-draft", "feedback", "scene-projection"), "invalid_source_role")
        require(ref.get("source_kind", "unknown") in ("user-supplied", "producer-output", "record-version", "sandbox-projection", "synthetic", "unknown"), "invalid_source_kind")
        if "feedback_target" in ref:
            require(value["kind"] == "writing" and ref.get("role") == "feedback", "invalid_relation")
            _exact_reference(ref["feedback_target"])
        require((value["kind"] == "writing" and ref["purpose"] != "actor-projection")
                or (value["kind"] == "world-action" and ref["purpose"] == "actor-projection"), "wrong_projection")
    require(len({ref["uri"] for ref in refs}) == len(refs), "duplicate_reference")
    return value


def writing_relations(value):
    """Validate selected writing roles and declared exact feedback applicability.

    This performs no reads. A record-backed caller must also compare feedback's
    durable review target with these declarations using its exact bindings.
    Material text and caller-reported roles never authenticate that relationship.
    """
    validate_request(value)
    require(value["kind"] == "writing", "unsupported_request_kind")
    phase = value.get("phase", "draft")
    refs = value["materials"]
    drafts = [ref for ref in refs if ref.get("role") == "current-draft"]
    feedback = [ref for ref in refs if ref.get("role") == "feedback"]
    require(len(drafts) <= 1, "invalid_relation")
    if phase in ("reader-review", "continuity-review", "revise") or feedback:
        require(len(drafts) == 1, "invalid_relation")
    if phase in ("reader-review", "continuity-review"):
        roles = ("current-draft", "prior-prose")
        if phase == "continuity-review":
            roles += ("scene-projection", "request-material")
        require(all(ref.get("role", "request-material") in roles for ref in refs), "invalid_relation")
    if phase == "revise":
        require(bool(feedback), "invalid_relation")
    if feedback:
        target = _reference(drafts[0])
        for ref in feedback:
            require("feedback_target" in ref, "feedback_target_required")
            require(ref["feedback_target"] == target, "feedback_target_mismatch")
    return {"draft": _reference(drafts[0]) if drafts else None,
            "feedback": [{"reference": _reference(ref),
                          "target": deepcopy(ref["feedback_target"])} for ref in feedback]}


def prepare(value, config_snapshot, *, resolver=None):
    validate_request(value)
    # A packet owns its declarations; later caller edits cannot retarget it.
    value, config_snapshot = deepcopy(value), deepcopy(config_snapshot)
    fields(config_snapshot, ("effective", "source", "sha256"))
    config = validate_config(config_snapshot["effective"])
    require(config_snapshot["source"] == "project-config"
            and digest(canonical(config)) == config_snapshot["sha256"], "changed_configuration")
    require(value["project_id"] == config["project_id"], "project_mismatch")
    require(value["kind"] != "world-action" or config["world_sandbox"], "sandbox_disabled")
    if value["kind"] == "writing" and config["writing_mode"] == "none":
        require(value.get("phase", "draft") in DIRECT_PHASES, "unsupported_phase")
    relations = writing_relations(value) if value["kind"] == "writing" else None
    technique_snapshot = None
    if value.get("techniques"):
        from writing_assistant.techniques import prepare_selection
        technique_snapshot = prepare_selection(value["techniques"], value.get("phase", "draft"))
    require(not value["materials"] or callable(resolver), "scoped_resolver_required")
    if value["kind"] == "writing" and value.get("phase") in ("reader-review", "continuity-review"):
        from writing_assistant.frameworks import prepare_review
        bridge = prepare_review(value, config["writing_mode"], resolver)
        packet = {"schema_version": "writing-assistant-packet/1", "request": value,
                  "configuration": config_snapshot, "context": "new-per-request",
                  "status": "prepared-unexecuted", "relations": relations, **bridge}
        _add_techniques(packet, technique_snapshot)
        packet["sha256"] = digest(canonical(packet))
        return packet
    visible, total = [], 0
    for ref in value["materials"]:
        # The trusted caller checks permission and exact record version first.
        # Neither a URI nor a document label grants permission.
        raw = resolver(deepcopy(ref))
        require(type(raw) is bytes and digest(raw) == ref["sha256"], "changed_reference")
        total += len(raw)
        require(total <= 4 * 1024 * 1024, "input_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            require(False, "unsupported_encoding")
        visible.append({"reference": deepcopy(ref), "text": text})
    packet = {"schema_version": "writing-assistant-packet/1", "request": value,
              "configuration": config_snapshot, "materials": visible,
              "instructions": [], "context": "new-per-request",
              "status": "prepared-unexecuted"}
    if relations is not None:
        packet["relations"] = relations
    # The method owner supplies Lotus instructions. Techniques are independent
    # and apply only through the exact explicit selection above.
    if value["kind"] == "writing" and config["writing_mode"] == "lotus":
        try:
            from writing_assistant.frameworks import prepare_lotus
        except ImportError:
            require(False, "lotus_component_unavailable")
        packet.update(prepare_lotus(value, visible))
    _add_techniques(packet, technique_snapshot)
    packet["sha256"] = digest(canonical(packet))
    return packet


def _add_techniques(packet, snapshot):
    if snapshot is not None:
        from writing_assistant.techniques import selection_instructions
        packet["techniques"] = snapshot
        packet["instructions"] = [*packet["instructions"], *selection_instructions(snapshot)]
