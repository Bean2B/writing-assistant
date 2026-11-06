"""Bounded, explicitly selected writing guidance from bundled JSON data."""

from copy import deepcopy
from pathlib import Path
import re

from .core.errors import AssistantError, require
from .core.interface import IDENTIFIER
from .core.jsonio import canonical, decode, digest, fields

PACK_SCHEMA = "writing-assistant-technique-pack/1"
SELECTION_SCHEMA = "writing-assistant-techniques/1"
PHASES = ("concept", "draft", "plan-scene", "reader-review", "continuity-review", "revise")
MAX_PACKS = 32
MAX_PACK_BYTES = 65536
MAX_PACK_TECHNIQUES = 16
MAX_SELECTED_PACKS = 8
MAX_SELECTED_TECHNIQUES = 16
SUGGESTION_SCHEMA = "writing-assistant-technique-suggestions/1"
MAX_SUGGESTIONS = 3
MAX_STORY_TAGS = 16
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")


def _text(value, limit):
    require(type(value) is str and bool(value.strip()), "invalid_technique_pack")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise AssistantError("invalid_technique_pack") from None
    require(size <= limit and not any(ord(char) < 32 and char not in "\n\t" for char in value),
            "invalid_technique_pack")


def _id(value):
    return type(value) is str and ID.fullmatch(value) is not None


def _version(value):
    return type(value) is str and len(value) <= 32 and VERSION.fullmatch(value) is not None


def _phases(value):
    require(type(value) is list and 1 <= len(value) <= len(PHASES)
            and all(type(item) is str and item in PHASES for item in value)
            and len(set(value)) == len(value), "invalid_technique_pack")


def _criteria(value):
    require(type(value) is list and 1 <= len(value) <= 8, "invalid_technique_pack")
    for item in value:
        _text(item, 1024)


def validate_pack(value):
    """Validate the complete data contract without reading files or executing code."""
    try:
        fields(value, ("schema_version", "pack_id", "pack_version", "title", "summary",
                       "guidance", "phase_guidance", "techniques"))
        require(value["schema_version"] == PACK_SCHEMA and _id(value["pack_id"])
                and _version(value["pack_version"]), "invalid_technique_pack")
        _text(value["title"], 120)
        _text(value["summary"], 1024)
        _text(value["guidance"], 2048)
        fields(value["phase_guidance"], PHASES)
        for text in value["phase_guidance"].values():
            _text(text, 2048)
        techniques = value["techniques"]
        require(type(techniques) is list and 1 <= len(techniques) <= MAX_PACK_TECHNIQUES,
                "invalid_technique_pack")
        for technique in techniques:
            fields(technique, ("technique_id", "title", "phases", "applies_when", "guidance",
                               "limitations", "review_criteria"), ("applicability",))
            require(_id(technique["technique_id"]), "invalid_technique_pack")
            _text(technique["title"], 120)
            _phases(technique["phases"])
            for key in ("applies_when", "guidance"):
                _text(technique[key], 2048)
            for key in ("limitations", "review_criteria"):
                _criteria(technique[key])
            if "applicability" in technique:
                selectors = technique["applicability"]
                fields(selectors, ("tasks", "story_tags"))
                for key, maximum in (("tasks", 8), ("story_tags", MAX_STORY_TAGS)):
                    items = selectors[key]
                    require(type(items) is list and 1 <= len(items) <= maximum
                            and all(_id(item) for item in items) and len(set(items)) == len(items),
                            "invalid_technique_pack")
        require(len({item["technique_id"] for item in techniques}) == len(techniques),
                "invalid_technique_pack")
        require(len(canonical(value)) <= MAX_PACK_BYTES, "technique_pack_limit")
    except AssistantError as error:
        if error.code in ("invalid_fields", "invalid_json"):
            raise AssistantError("invalid_technique_pack") from None
        raise
    return deepcopy(value)


def _bounded_entries(directory):
    entries = []
    for entry in directory.iterdir():
        require(len(entries) < MAX_PACKS, "technique_pack_limit")
        entries.append(entry)
    return sorted(entries, key=lambda entry: entry.name)


def _paths():
    # The package is the only authority for extensions. No request or project
    # setting can supply a search path, executable loader, or replacement pack.
    root = Path(__file__).with_name("technique_packs")
    try:
        require(not root.is_symlink() and root.is_dir(), "invalid_technique_pack")
        result = []
        for directory in _bounded_entries(root):
            require(_id(directory.name) and not directory.is_symlink() and directory.is_dir(),
                    "invalid_technique_pack")
            versions = _bounded_entries(directory)
            require(bool(versions), "invalid_technique_pack")
            for path in versions:
                require(len(result) < MAX_PACKS, "technique_pack_limit")
                require(path.suffix == ".json" and _version(path.stem)
                        and not path.is_symlink() and path.is_file(), "invalid_technique_pack")
                result.append((directory.name, path.stem, path))
        require(bool(result), "invalid_technique_pack")
        return result
    except OSError:
        raise AssistantError("invalid_technique_pack") from None


def _read(path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_PACK_BYTES + 1)
    except OSError:
        raise AssistantError("invalid_technique_pack") from None
    require(len(raw) <= MAX_PACK_BYTES, "technique_pack_limit")
    return raw


def _load(pack_id, pack_version, path):
    raw = _read(path)
    try:
        pack = validate_pack(decode(raw))
    except AssistantError as error:
        if error.code in ("duplicate_key", "invalid_json", "input_limit"):
            raise AssistantError("invalid_technique_pack") from None
        raise
    require(pack["pack_id"] == pack_id and pack["pack_version"] == pack_version,
            "invalid_technique_pack")
    return {**pack, "sha256": digest(raw)}


def source_digests():
    """Bind bounded bundled bytes into an execution policy without applying guidance."""
    return {"technique_packs/" + pack_id + "/" + version + ".json": digest(_read(path))
            for pack_id, version, path in _paths()}


def list_packs():
    """Return deterministic discovery metadata; never select or apply a technique."""
    result = []
    for pack_id, version, path in _paths():
        pack = _load(pack_id, version, path)
        result.append({key: pack[key] for key in ("pack_id", "pack_version", "sha256", "title", "summary")} |
                      {"phases": [phase for phase in PHASES
                                  if any(phase in item["phases"] for item in pack["techniques"])],
                       "technique_ids": sorted(item["technique_id"] for item in pack["techniques"])})
    return result


def show_pack(pack_id, pack_version=None):
    """Return one exact pack; omitted version chooses the highest numeric version."""
    require(_id(pack_id) and (pack_version is None or _version(pack_version)),
            "invalid_technique_selection")
    matches = [(version, path) for identity, version, path in _paths()
               if identity == pack_id and (pack_version is None or version == pack_version)]
    require(bool(matches), "technique_pack_not_found")
    version, path = max(matches, key=lambda row: tuple(int(part) for part in row[0].split(".")))
    return _load(pack_id, version, path)


def validate_selection(value):
    """Validate explicit exact selections without loading pack data."""
    try:
        require(type(value) is list and len(value) <= MAX_SELECTED_PACKS, "invalid_technique_selection")
        total = 0
        for selected in value:
            fields(selected, ("pack_id", "pack_version", "pack_sha256", "technique_ids"))
            require(_id(selected["pack_id"]) and _version(selected["pack_version"])
                    and type(selected["pack_sha256"]) is str and HASH.fullmatch(selected["pack_sha256"]),
                    "invalid_technique_selection")
            ids = selected["technique_ids"]
            require(type(ids) is list and 1 <= len(ids) <= MAX_SELECTED_TECHNIQUES
                    and all(_id(item) for item in ids), "invalid_technique_selection")
            require(len(set(ids)) == len(ids), "duplicate_technique_selection")
            total += len(ids)
        require(total <= MAX_SELECTED_TECHNIQUES, "invalid_technique_selection")
        require(len({item["pack_id"] for item in value}) == len(value), "duplicate_technique_selection")
    except AssistantError as error:
        if error.code == "invalid_fields":
            raise AssistantError("invalid_technique_selection") from None
        raise
    return deepcopy(value)


def prepare_selection(value, phase):
    """Freeze exact selected guidance before material reads or model dispatch."""
    selected = validate_selection(value)
    require(type(phase) is str and phase in PHASES, "unsupported_phase")
    packs = []
    for item in sorted(selected, key=lambda row: row["pack_id"]):
        pack = show_pack(item["pack_id"], item["pack_version"])
        require(pack["sha256"] == item["pack_sha256"], "changed_technique_pack")
        available = {row["technique_id"]: row for row in pack["techniques"]}
        require(all(identity in available for identity in item["technique_ids"]), "unknown_technique")
        techniques = [available[identity] for identity in sorted(item["technique_ids"])]
        require(all(phase in row["phases"] for row in techniques), "technique_not_applicable")
        packs.append({"pack_id": pack["pack_id"], "pack_version": pack["pack_version"],
                      "pack_sha256": pack["sha256"], "title": pack["title"],
                      "guidance": pack["guidance"], "phase_guidance": pack["phase_guidance"][phase],
                      "techniques": techniques})
    return {"schema_version": SELECTION_SCHEMA, "phase": phase, "packs": packs}


def suggest(phase, *, task, story_tags, limit=MAX_SUGGESTIONS):
    """Suggest a small set using declared selectors, without choosing or applying it.

    Only the newest bundled version of each pack participates. Unannotated packs
    remain selectable but are never guessed applicable from their prose. Adding
    a matching pack can alter this discovery result, never a prepared selection.
    """
    require(type(phase) is str and phase in PHASES, "unsupported_phase")
    require(_id(task) and type(story_tags) is list and len(story_tags) <= MAX_STORY_TAGS
            and all(type(tag) is str and IDENTIFIER.fullmatch(tag) for tag in story_tags)
            and len(set(story_tags)) == len(story_tags)
            and type(limit) is int and 0 <= limit <= MAX_SUGGESTIONS, "invalid_technique_suggestion")
    tags = sorted(story_tags)
    result = {"contract": SUGGESTION_SCHEMA, "phase": phase, "task": task, "story_tags": tags,
              "limit": limit, "suggestions": [], "suggested_selection": [], "omitted_matches": 0,
              "selection_applied": False, "model_calls": 0}
    # Zero and an empty tag set are complete choices, with no guidance discovery.
    if not limit or not tags:
        return result
    newest = {}
    for pack_id, version, path in _paths():
        numeric = tuple(int(part) for part in version.split("."))
        if pack_id not in newest or numeric > newest[pack_id][0]:
            newest[pack_id] = (numeric, version, path)
    matches = []
    for pack_id, (_, version, path) in sorted(newest.items()):
        pack = _load(pack_id, version, path)
        for technique in pack["techniques"]:
            selectors = technique.get("applicability")
            if selectors is None or phase not in technique["phases"] or task not in selectors["tasks"]:
                continue
            matched = sorted(set(tags) & set(selectors["story_tags"]))
            if not matched:
                continue
            matches.append({"pack_id": pack_id, "pack_version": version, "pack_sha256": pack["sha256"],
                            "technique_id": technique["technique_id"], "title": technique["title"],
                            "matched_tags": matched,
                            "reasons": ["Declared phase: " + phase + ".", "Declared task: " + task + ".",
                                        "Explicit matching story tags: " + ", ".join(matched) + "."]})
    # More explicit selector matches rank first; exact identities break ties.
    matches.sort(key=lambda row: (-len(row["matched_tags"]), row["pack_id"], row["technique_id"]))
    result["suggestions"] = matches[:limit]
    result["omitted_matches"] = len(matches) - len(result["suggestions"])
    selected = {}
    for row in result["suggestions"]:
        if row["pack_id"] not in selected:
            selected[row["pack_id"]] = {key: row[key] for key in ("pack_id", "pack_version", "pack_sha256")}
            selected[row["pack_id"]]["technique_ids"] = []
        selected[row["pack_id"]]["technique_ids"].append(row["technique_id"])
    result["suggested_selection"] = [{**selected[key], "technique_ids": sorted(selected[key]["technique_ids"])}
                                     for key in sorted(selected)]
    return result


def selection_instructions(snapshot):
    """Render the frozen snapshot, without rediscovering or changing its selection."""
    instructions = []
    for pack in snapshot["packs"]:
        lines = ["Selected writing techniques: " + pack["title"], pack["guidance"], pack["phase_guidance"]]
        for technique in pack["techniques"]:
            lines.extend([technique["title"], "Apply when: " + technique["applies_when"], technique["guidance"],
                          "Limits: " + " ".join(technique["limitations"]),
                          "Optional review lenses: " + " ".join(technique["review_criteria"])])
        instructions.append("\n".join(lines))
    return instructions
