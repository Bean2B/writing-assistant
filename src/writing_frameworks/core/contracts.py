"""Bounded producer references, not a creative-record database schema."""
from __future__ import annotations

import hashlib
import json
import re

CONTRACT_VERSION = 1
MAX_MATERIALS = 32
MAX_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 4 * MAX_BYTES


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise ContractError(code, message)


def fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value)
            and set(value) <= set(required) | set(optional),
            "invalid_contract", "Unexpected or missing contract fields.")


def text(value):
    return type(value) is str and bool(value.strip())


def utf8(value):
    require(type(value) is str, "invalid_text", "UTF-8 text is required.")
    try:
        return value.encode("utf-8")
    except UnicodeError as error:
        raise ContractError("invalid_text", "Text cannot be represented as UTF-8.") from error


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ContractError("invalid_contract", "Value is not bounded UTF-8 JSON.") from error


def digest(raw):
    require(type(raw) is bytes, "invalid_bytes", "Original content must be bytes.")
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_key", "Duplicate JSON keys are not accepted.")
            result[key] = value
        return result

    def nonfinite(_value):
        raise ContractError("invalid_json", "Non-finite JSON values are not accepted.")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError("invalid_json", "Input is not valid JSON.") from error


def reference(value):
    """Validate a caller-owned immutable reference without resolving its URI."""
    fields(value, ("uri", "sha256"))
    require(text(value["uri"]) and len(value["uri"]) <= 2048,
            "invalid_reference", "A bounded producer URI is required.")
    utf8(value["uri"])
    require(type(value["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
            "invalid_reference", "An exact SHA-256 is required.")
    return dict(value)


def bind(uri, raw):
    return reference({"uri": uri, "sha256": digest(raw)})


def materials(refs, resolver):
    require(type(refs) is list and len(refs) <= MAX_MATERIALS,
            "input_limit", "Too many material references.")
    validated = [reference(item) for item in refs]
    require(not validated or callable(resolver), "resolver_required",
            "Material access requires an explicitly supplied scoped resolver.")
    result, total = [], 0
    for ref in validated:
        # The owner must enforce permission before returning bytes. No filesystem,
        # registry or network fallback is provided here.
        raw = resolver(dict(ref))
        require(type(raw) is bytes, "invalid_bytes", "The scoped resolver must return bytes.")
        total += len(raw)
        require(len(raw) <= MAX_BYTES and total <= MAX_TOTAL_BYTES,
                "input_limit", "Selected material exceeds the byte budget.")
        require(digest(raw) == ref["sha256"], "changed_reference", "Selected material no longer matches its reference.")
        try:
            body = raw.decode("utf-8")
        except UnicodeError as error:
            raise ContractError("invalid_material", "Writing materials must be UTF-8 text.") from error
        result.append({"reference": ref, "text": body})
    return result
