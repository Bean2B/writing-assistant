"""Evidence-bound review companions. Validation does not decide literary truth."""

from copy import deepcopy
import re

from .core.errors import AssistantError, require
from .core.jsonio import canonical, decode, digest, fields

CONTRACT = "writing-assistant-review-decision/1"
OUTPUT_CONTRACT = "writing-assistant-review-output/1"
MAX_OUTPUT_BYTES = 131072
MAX_DECISION_BYTES = 524288
MAX_OBSERVATIONS = 32
MAX_EVIDENCE = 8
MAX_MATERIALS = 64
MAX_MATERIAL_BYTES = 16777216
MAX_CHOICES = 128
MAX_OCCURRENCES = 4096
CLASSIFICATIONS = ("confirmed-contradiction", "uncertainty", "preference")
DISPOSITIONS = ("proposed", "accepted", "rejected", "deferred")
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")


def _text(value, maximum=4096, *, code="invalid_review_decision"):
    require(type(value) is str and bool(value.strip()), code)
    try:
        require(len(value.encode("utf-8")) <= maximum, code)
    except UnicodeError:
        raise AssistantError(code) from None
    require(not any(ord(char) < 32 and char not in "\r\n\t" for char in value), code)
    return value


def _reference(value):
    fields(value, ("contract", "project_id", "record_id", "version_id", "sha256"))
    require(value["contract"] == "creative-records/1" and all(
        type(value[key]) is str and ID.fullmatch(value[key])
        for key in ("project_id", "record_id", "version_id")), "invalid_review_decision")
    require(type(value["sha256"]) is str and HASH.fullmatch(value["sha256"]),
            "invalid_review_decision")


def _raw(value, *, code="invalid_review_decision", maximum=MAX_MATERIAL_BYTES):
    try:
        raw = value.encode("utf-8") if type(value) is str else value
        require(type(raw) is bytes and len(raw) <= maximum, code)
        raw.decode("utf-8")
        return raw
    except UnicodeError:
        raise AssistantError(code) from None


def exact_span(text, quote, occurrence=None):
    """Resolve a literal quote to a UTF-8 half-open byte range, without guessing.

    An omitted occurrence is accepted only for a unique quote. Occurrences are
    one-based, include overlapping matches, and count bytes in the exact original.
    """
    raw = _raw(text)
    needle = _raw(_text(quote, 8192))
    require(occurrence is None or type(occurrence) is int and 1 <= occurrence <= MAX_OCCURRENCES,
            "invalid_review_decision")
    first = raw.find(needle)
    require(first >= 0, "review_quote_not_found")
    if occurrence is None:
        require(raw.find(needle, first + 1) < 0, "ambiguous_review_quote")
        start = first
    else:
        start = first
        for _ in range(occurrence - 1):
            start = raw.find(needle, start + 1)
            require(start >= 0, "review_quote_not_found")
    return {"byte_start": start, "byte_end": start + len(needle), "quote": quote}


def _span(value):
    fields(value, ("byte_start", "byte_end", "quote"))
    require(type(value["byte_start"]) is int and type(value["byte_end"]) is int
            and 0 <= value["byte_start"] < value["byte_end"] <= MAX_MATERIAL_BYTES,
            "invalid_review_decision")
    _text(value["quote"], 8192)
    require(len(value["quote"].encode("utf-8")) == value["byte_end"] - value["byte_start"],
            "invalid_review_decision")


def _range(value, maximum=MAX_MATERIAL_BYTES):
    fields(value, ("byte_start", "byte_end"))
    require(type(value["byte_start"]) is int and type(value["byte_end"]) is int
            and 0 <= value["byte_start"] < value["byte_end"] <= maximum,
            "invalid_review_decision")


def _choice(value):
    fields(value, ("observation_id", "disposition", "reason"))
    require(type(value["observation_id"]) is str and ID.fullmatch(value["observation_id"])
            and value["disposition"] in DISPOSITIONS[1:], "invalid_review_choice")
    _text(value["reason"], code="invalid_review_choice")


def validate_decision(value):
    """Check the saved companion contract, including its original-output digest.

    This structural check cannot re-read source bodies. Use verify_decision with
    the exact selected originals when consuming a saved companion for progression.
    """
    try:
        fields(value, ("schema_version", "target", "original_output", "review_text", "outcome",
                       "observations", "choices", "verification", "literary_correctness"))
        require(value["schema_version"] == CONTRACT and value["verification"] == "targets-and-evidence-verified"
                and value["literary_correctness"] == "not-mechanically-determined", "invalid_review_decision")
        _reference(value["target"])
        fields(value["original_output"], ("text", "sha256"))
        original = _raw(value["original_output"]["text"], maximum=MAX_OUTPUT_BYTES)
        require(digest(original) == value["original_output"]["sha256"], "invalid_review_decision")
        _text(value["review_text"], 32768)
        observations = value["observations"]
        require(type(observations) is list and len(observations) <= MAX_OBSERVATIONS,
                "invalid_review_decision")
        require(value["outcome"] in ("concerns", "no-concerns")
                and (value["outcome"] == "concerns") == bool(observations), "invalid_review_decision")
        identities = set()
        for row in observations:
            fields(row, ("observation_id", "span", "observation", "classification", "impact",
                         "proposed_change", "evidence", "disposition", "user_choice"))
            identity = row["observation_id"]
            require(type(identity) is str and ID.fullmatch(identity) and identity not in identities,
                    "invalid_review_decision")
            identities.add(identity)
            _span(row["span"])
            for key in ("observation", "proposed_change"):
                _text(row[key])
            require(row["classification"] in CLASSIFICATIONS and row["impact"] in ("material", "minor")
                    and row["disposition"] in DISPOSITIONS, "invalid_review_decision")
            require(type(row["evidence"]) is list and len(row["evidence"]) <= MAX_EVIDENCE
                    and (row["classification"] != "confirmed-contradiction" or bool(row["evidence"])),
                    "invalid_review_decision")
            seen = set()
            for evidence in row["evidence"]:
                fields(evidence, ("material_id", "ref", "span"), ("selected_range",))
                require(type(evidence["material_id"]) is str and re.fullmatch(
                    r"target|evidence-([1-9][0-9]?)", evidence["material_id"]), "invalid_review_decision")
                _reference(evidence["ref"])
                require(evidence["ref"]["project_id"] == value["target"]["project_id"],
                        "invalid_review_decision")
                _span(evidence["span"])
                if "selected_range" in evidence:
                    _range(evidence["selected_range"])
                    require(evidence["selected_range"]["byte_start"] <= evidence["span"]["byte_start"]
                            and evidence["span"]["byte_end"] <= evidence["selected_range"]["byte_end"],
                            "invalid_review_decision")
                key = canonical(evidence)
                require(key not in seen, "invalid_review_decision")
                seen.add(key)
            if row["user_choice"] is not None:
                _choice(row["user_choice"])
                require(row["user_choice"]["observation_id"] == identity
                        and row["user_choice"]["disposition"] == row["disposition"], "invalid_review_decision")
            else:
                require(row["disposition"] == "proposed", "invalid_review_decision")
        require(type(value["choices"]) is list and len(value["choices"]) <= MAX_CHOICES,
                "invalid_review_decision")
        latest = {}
        for choice in value["choices"]:
            _choice(choice)
            require(choice["observation_id"] in identities, "invalid_review_decision")
            latest[choice["observation_id"]] = choice
        require(all(row["user_choice"] == latest.get(row["observation_id"]) for row in observations),
                "invalid_review_decision")
        require(len(canonical(value)) <= MAX_DECISION_BYTES, "review_decision_limit")
    except (TypeError, KeyError):
        raise AssistantError("invalid_review_decision") from None
    except AssistantError as error:
        if error.code in ("invalid_fields", "invalid_json", "invalid_review_choice"):
            raise AssistantError("invalid_review_decision") from None
        raise
    return deepcopy(value)


def _sources(target_ref, target_text, evidence):
    _reference(target_ref)
    require(type(evidence) in (list, tuple) and len(evidence) <= MAX_MATERIALS, "invalid_review_decision")
    sources = {"target": {"ref": target_ref, "raw": _raw(target_text)}}
    for index, item in enumerate(evidence, 1):
        fields(item, ("ref", "text"), ("range",))
        _reference(item["ref"])
        require(item["ref"]["project_id"] == target_ref["project_id"], "invalid_review_decision")
        source = {"ref": item["ref"], "raw": _raw(item["text"])}
        if "range" in item:
            _range(item["range"], len(source["raw"]))
            source["selected_range"] = deepcopy(item["range"])
        sources["evidence-" + str(index)] = source
    require(sum(len(row["raw"]) for row in sources.values()) <= MAX_MATERIAL_BYTES,
            "review_material_limit")
    require(all(digest(row["raw"]) == row["ref"]["sha256"] for row in sources.values()),
            "changed_review_reference")
    for source in sources.values():
        if "selected_range" in source:
            selected = source["selected_range"]
            source["raw"] = _raw(source["raw"][selected["byte_start"]:selected["byte_end"]])
    return sources


def parse_review_output(text, *, target_ref, target_text, evidence=()):
    """Parse a bounded model companion and bind literal quotes to selected bytes."""
    raw = _raw(text, code="invalid_review_output", maximum=MAX_OUTPUT_BYTES)
    stripped = raw.strip()
    require(bool(stripped), "review_decisions_missing")
    fenced = re.fullmatch(rb"```(?:json)?[ \t]*\r?\n([\s\S]*)\r?\n```", stripped, re.IGNORECASE)
    if fenced:
        stripped = fenced[1].strip()
    require(stripped.startswith(b"{"), "review_decisions_missing")
    try:
        output = decode(stripped)
        fields(output, ("schema_version", "review_text", "outcome", "observations"))
        require(output["schema_version"] == OUTPUT_CONTRACT, "invalid_review_output")
        _text(output["review_text"], 32768, code="invalid_review_output")
        require(type(output["observations"]) is list and len(output["observations"]) <= MAX_OBSERVATIONS,
                "invalid_review_output")
        require(output["outcome"] in ("concerns", "no-concerns") and
                (output["outcome"] == "concerns") == bool(output["observations"]), "invalid_review_output")
        sources = _sources(target_ref, target_text, evidence)
        observations = []
        for row in output["observations"]:
            fields(row, ("observation_id", "span", "observation", "classification", "impact",
                         "proposed_change", "evidence"))
            fields(row["span"], ("quote",), ("occurrence",))
            span = exact_span(sources["target"]["raw"], **row["span"])
            require(type(row["evidence"]) is list and len(row["evidence"]) <= MAX_EVIDENCE,
                    "invalid_review_output")
            resolved = []
            for item in row["evidence"]:
                fields(item, ("material_id", "quote"), ("occurrence",))
                require(type(item["material_id"]) is str and item["material_id"] in sources,
                        "review_evidence_not_selected")
                source = sources[item["material_id"]]
                citation = {"material_id": item["material_id"], "ref": deepcopy(source["ref"]),
                            "span": exact_span(source["raw"], item["quote"], item.get("occurrence"))}
                if "selected_range" in source:
                    citation["selected_range"] = deepcopy(source["selected_range"])
                    offset = source["selected_range"]["byte_start"]
                    citation["span"]["byte_start"] += offset
                    citation["span"]["byte_end"] += offset
                resolved.append(citation)
            observations.append({**row, "span": span, "evidence": resolved,
                                 "disposition": "proposed", "user_choice": None})
        result = {"schema_version": CONTRACT, "target": deepcopy(target_ref),
                  "original_output": {"text": raw.decode("utf-8"), "sha256": digest(raw)},
                  "review_text": output["review_text"], "outcome": output["outcome"],
                  "observations": observations, "choices": [],
                  "verification": "targets-and-evidence-verified",
                  "literary_correctness": "not-mechanically-determined"}
        return validate_decision(result)
    except (TypeError, KeyError):
        raise AssistantError("invalid_review_output") from None
    except AssistantError as error:
        if error.code in ("invalid_fields", "invalid_json", "duplicate_key", "invalid_review_decision"):
            raise AssistantError("invalid_review_output") from None
        raise


def verify_decision(value, *, target_ref, target_text, evidence=()):
    """Revalidate a saved companion against the selected originals and choices."""
    saved = validate_decision(value)
    rebuilt = parse_review_output(saved["original_output"]["text"], target_ref=target_ref,
                                  target_text=target_text, evidence=evidence)
    rebuilt = validate_choice(rebuilt, saved["choices"])
    require(rebuilt == saved, "changed_review_decision")
    return rebuilt


def validate_choice(decision, observations):
    """Apply explicit feedback dispositions, retaining rejected choices and history.

    Callers own user authorization. Accepting feedback never adopts prose or facts.
    Exact repetitions are idempotent; a changed choice appends to the history.
    """
    result = validate_decision(decision)
    require(type(observations) is list and len(observations) <= MAX_CHOICES, "invalid_review_choice")
    by_id = {row["observation_id"]: row for row in result["observations"]}
    for choice in observations:
        try:
            _choice(choice)
        except (TypeError, KeyError, AssistantError):
            raise AssistantError("invalid_review_choice") from None
        require(choice["observation_id"] in by_id, "unknown_review_observation")
        row = by_id[choice["observation_id"]]
        if row["user_choice"] == choice:
            continue
        require(len(result["choices"]) < MAX_CHOICES, "review_choice_limit")
        row["disposition"] = choice["disposition"]
        row["user_choice"] = deepcopy(choice)
        result["choices"].append(deepcopy(choice))
    return validate_decision(result)


def review_instructions(target_ref, evidence_refs=()):
    """Describe the strict companion format and ordered material aliases."""
    _reference(target_ref)
    require(type(evidence_refs) in (list, tuple) and len(evidence_refs) <= MAX_MATERIALS,
            "invalid_review_decision")
    aliases = [{"material_id": "target", "ref": target_ref}]
    for index, reference in enumerate(evidence_refs, 1):
        _reference(reference)
        require(reference["project_id"] == target_ref["project_id"], "invalid_review_decision")
        aliases.append({"material_id": "evidence-" + str(index), "ref": reference})
    example = {"schema_version": OUTPUT_CONTRACT, "review_text": "Your complete original review prose.",
               "outcome": "concerns", "observations": [{"observation_id": "concern-1",
                   "span": {"quote": "EXACT literal draft quote", "occurrence": 1},
                   "observation": "Describe the concern and its supported scope.",
                   "classification": "uncertainty", "impact": "material",
                   "proposed_change": "One bounded proposed repair or clarification.",
                   "evidence": [{"material_id": "target", "quote": "EXACT literal supporting quote",
                                 "occurrence": 1}]}]}
    return ("Return one JSON object in this format, with no surrounding prose: " + canonical(example).decode("utf-8")
            + "\nThe complete original review belongs in review_text. Use at most 32 observations and 8 evidence "
              "citations per observation. Every span and evidence quote must copy literal selected text exactly, "
              "including punctuation and whitespace. occurrence is one-based among overlapping occurrences in the "
              "displayed selected text only, bounded to 4096; "
              "omit it only for a unique quote. Do not calculate offsets. Use classification confirmed-contradiction "
              "only for a reviewer-asserted contradiction supported by at least one selected citation; use uncertainty "
              "for gaps or uncertain inferences and preference for subjective alternatives. impact is material or minor. "
              "These labels are review claims, never proof of literary correctness or adopted facts. Provisional plans "
              "and generated proposals do not establish canon. For no identified concerns use outcome no-concerns and "
              "observations [], while retaining a substantive review_text. Do not mark unavailable material as reviewed. "
              "Do not add disposition or user-choice fields. Evidence aliases follow the corresponding selected "
              "material order: " + canonical(aliases).decode("utf-8"))
