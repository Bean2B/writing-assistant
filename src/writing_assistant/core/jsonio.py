import hashlib
import json

from .errors import AssistantError, require

MAX_BYTES = 4 * 1024 * 1024


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise AssistantError("invalid_json") from None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES, "input_limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_key")
            result[key] = value
        return result

    def finite(_):
        raise AssistantError("invalid_json")

    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=finite)
    except (ValueError, UnicodeError, RecursionError):
        raise AssistantError("invalid_json") from None


def fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value)
            and set(value) <= set(required) | set(optional), "invalid_fields")
