"""Thin explicit producer references; never imports or runs optional producers."""
from dataclasses import dataclass
from pathlib import Path

from .safeio import SafeSession
from .core import RecordsError, digest, encoded, identifier, keys, require, sha, strict_json

WRITER_FORMAT = "lotus-writing-producer/1@0.1.0"
SANDBOX_FORMAT = "lotus-runstore-actor-view/1"


@dataclass(frozen=True)
class ArtifactBinding:
    project_id: str
    audiences: frozenset
    descriptor: dict
    relative_path: str


class BoundArtifacts:
    """Explicit host-approved paths only; not automatic source discovery/grants."""

    def __init__(self, root, bindings):
        self.root = Path(root)
        self.bindings = tuple(bindings)

    def __call__(self, descriptor, scope):
        scope.verify()
        matches = [b for b in self.bindings if b.project_id == scope.project_id and
                   scope.audience in b.audiences and b.descriptor == descriptor]
        require(len(matches) == 1, "reference_unavailable")
        binding = matches[0]
        require(not Path(binding.relative_path).is_absolute(), "reference_unavailable")
        try:
            with SafeSession(self.root) as io:
                raw = io.read_bytes(binding.relative_path, expected_sha256=descriptor["sha256"])
                scope.verify()
                return raw
        except RecordsError as error:
            if error.code == "authority_failed":
                raise RecordsError("authority_failed") from None
            raise RecordsError("reference_unavailable") from None
        except (ValueError, OSError):
            raise RecordsError("reference_unavailable") from None


def _opaque_ref(value):
    keys(value, "uri sha256")
    require(isinstance(value["uri"], str) and bool(value["uri"].strip()) and len(value["uri"]) <= 2048, "unsupported_producer")
    sha(value["sha256"])


def register_writer_output(store, scope, *, operation_id, envelope, reference, parent=None,
                           title="", work_id=None):
    """Consume the pinned 0.1.0 producer envelope, without claiming host proof."""
    store._validate_external(reference)
    keys(envelope, "schema_version producer component_version request_id packet_sha256 selection phase method_version inputs output byte_length parent origin origin_assurance disposition")
    require(type(envelope["schema_version"]) is int and envelope["schema_version"] == 1 and
            envelope["producer"] == "lotus-writing-producer" and envelope["component_version"] == "0.1.0", "unsupported_producer")
    require(reference["producer"] == "writing-framework" and reference["version"] == WRITER_FORMAT, "unsupported_producer")
    _opaque_ref(envelope["output"])
    sha(envelope["packet_sha256"])
    require(isinstance(envelope["request_id"], str) and bool(envelope["request_id"].strip()) and len(envelope["request_id"]) <= 256, "unsupported_producer")
    require(type(envelope["byte_length"]) is int and envelope["byte_length"] >= 0 and
            envelope["output"]["sha256"] == reference["sha256"], "stale_reference")
    keys(envelope["origin"], "host execution_ref status evidence_kind")
    require(envelope["origin"]["host"] == "codex" and isinstance(envelope["origin"]["status"], str) and envelope["origin"]["status"] in
            {"completed", "failed", "cancelled", "unknown"} and isinstance(envelope["origin"]["evidence_kind"], str) and envelope["origin"]["evidence_kind"] in
            {"synthetic", "supplied-output", "host-observation"}, "unsupported_producer")
    execution_ref = envelope["origin"]["execution_ref"]
    require(execution_ref is None or isinstance(execution_ref, str) and bool(execution_ref.strip()) and len(execution_ref) <= 2048, "unsupported_producer")
    require(envelope["origin_assurance"] == "caller-reported-not-authenticated" and
            envelope["disposition"] == "unadopted-producer-output", "unsupported_producer")
    require(isinstance(envelope["inputs"], list) and len(envelope["inputs"]) <= 32, "unsupported_producer")
    keys(envelope["selection"], "version mode")
    mode = envelope["selection"]["mode"]
    require(type(envelope["selection"]["version"]) is int and envelope["selection"]["version"] == 1 and
            isinstance(mode, str) and mode in {"lotus", "none"}, "unsupported_producer")
    phases = {"none": {"draft", "reader-review", "continuity-review"},
              "lotus": {"plan-scene", "draft", "reader-review", "continuity-review", "revise"}}
    require(isinstance(envelope["phase"], str) and envelope["phase"] in phases[mode], "unsupported_producer")
    require((mode == "none" and envelope["method_version"] is None) or
            (mode == "lotus" and type(envelope["method_version"]) is int and envelope["method_version"] == 1), "unsupported_producer")
    for item in envelope["inputs"]:
        _opaque_ref(item)
    if envelope["parent"] is not None:
        _opaque_ref(envelope["parent"])
    scope.verify(write=True)
    raw = store._resolve(reference, scope)
    require(len(raw) == envelope["byte_length"] and digest(raw) == reference["sha256"], "stale_reference")
    # Retain the complete producer envelope as descriptive provenance. This is
    # not a second content store or proof that a reported execution occurred.
    origin = encoded(envelope).decode("utf-8").rstrip("\n")
    return store.save(scope, operation_id=operation_id, body=raw, title=title,
                      kind="feedback" if envelope["phase"] in {"reader-review", "continuity-review"} else "draft", work_id=work_id,
                      source={"authorship": "unknown", "origin": origin}, parent=parent, reference=reference)


def register_actor_projection(store, scope, *, operation_id, reference, actor_id, source_version,
                              title="", work_id=None):
    """Reference an already-approved actor_view export, never an owner snapshot."""
    store._validate_external(reference)
    identifier(actor_id)
    require(reference["producer"] == "world-sandbox" and reference["version"] == SANDBOX_FORMAT, "unsupported_producer")
    sha(source_version)
    scope.verify(write=True)
    raw = store._resolve(reference, scope)
    require(digest(raw) == reference["sha256"], "stale_reference")
    projection = strict_json(raw)
    keys(projection, "actor_id profile trajectory observation")
    require(projection["actor_id"] == actor_id and isinstance(projection["profile"], dict) and
            isinstance(projection["trajectory"], list) and isinstance(projection["observation"], dict), "unsupported_producer")
    origin = {"producer": "world-sandbox", "format": SANDBOX_FORMAT, "actor_id": actor_id,
              "source_version": source_version, "projection_sha256": reference["sha256"],
              "assurance": "caller-selected-producer-projection-not-semantic-spoiler-proof"}
    return store.save(scope, operation_id=operation_id, body=raw, title=title, kind="setting", work_id=work_id,
                      source={"authorship": "unknown", "origin": encoded(origin).decode().rstrip("\n")}, reference=reference)
