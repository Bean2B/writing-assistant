"""Project configuration. Changes take effect only at execution boundaries."""

from pathlib import Path
import os
import re

from .errors import AssistantError, require
from .files import atomic, directory_chain, lock, read
from .jsonio import canonical, decode, digest, fields

CONFIG = ".writing-assistant/config.json"
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def physical_separation(project, data_dir, *, create=False):
    # Compare actual directory ancestry, covering case-insensitive names and
    # alternate root spellings as well as normalized lexical paths.
    with directory_chain(project, create=create) as (_project_fd, projects):
        with directory_chain(data_dir, create=create) as (_data_fd, data):
            require(projects[-1] not in data and data[-1] not in projects, "data_source_overlap")


def validate(value):
    fields(value, ("schema_version", "project_id", "data_dir", "writing_mode",
                   "world_sandbox", "codex_adapter"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "unsupported_config_version")
    require(type(value["project_id"]) is str and ID.fullmatch(value["project_id"]), "invalid_project_id")
    require(type(value["data_dir"]) is str and "\0" not in value["data_dir"]
            and Path(value["data_dir"]).is_absolute()
            and os.path.abspath(value["data_dir"]) == value["data_dir"], "invalid_data_dir")
    require(type(value["writing_mode"]) is str and value["writing_mode"] in ("lotus", "none"), "unavailable_mode")
    require(type(value["world_sandbox"]) is bool, "invalid_sandbox_setting")
    require(value["codex_adapter"] == "codex-exec/1", "unsupported_adapter")
    return dict(value)


def initialize(project, data_dir, project_id, *, writing_mode="lotus", world_sandbox=True):
    project = Path(os.path.abspath(project))
    data_dir = Path(os.path.abspath(data_dir))
    require(not data_dir.is_relative_to(project) and not project.is_relative_to(data_dir), "data_source_overlap")
    value = validate({"schema_version": 1, "project_id": project_id, "data_dir": str(data_dir),
                      "writing_mode": writing_mode, "world_sandbox": world_sandbox, "codex_adapter": "codex-exec/1"})
    physical_separation(project, data_dir, create=True)
    atomic(project, CONFIG, canonical(value) + b"\n", exclusive=True)
    return snapshot(project)


def load(project):
    try:
        value = validate(decode(read(project, CONFIG, limit=16384)))
        data_dir = Path(value["data_dir"])
        project = Path(os.path.abspath(project))
        require(not data_dir.is_relative_to(project) and not project.is_relative_to(data_dir), "data_source_overlap")
        physical_separation(project, data_dir)
        return value
    except FileNotFoundError:
        raise AssistantError("project_not_initialized") from None


def snapshot(project):
    value = load(project)
    return {"effective": value, "source": "project-config", "sha256": digest(canonical(value))}


def change(project, *, writing_mode=None, world_sandbox=None):
    # Keep this transaction short. World operations poll persistent settings
    # without retaining this lock across a decision callback.
    with lock(project, ".writing-assistant/operation.lock"):
        value = load(project)
        previous = value["writing_mode"]
        if writing_mode is not None:
            value["writing_mode"] = writing_mode
        if world_sandbox is not None:
            value["world_sandbox"] = world_sandbox
        validate(value)
        atomic(project, CONFIG, canonical(value) + b"\n")
    return {**snapshot(project), "new_context_required": previous == "lotus" and value["writing_mode"] == "none",
            "message": "Each generation uses a new context; changing configuration does not erase an existing chat."}
