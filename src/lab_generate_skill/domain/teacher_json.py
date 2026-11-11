"""Finite exact JSON evidence values, without I/O or implicit type coercion."""

import json
import math
from typing import cast
from pydantic import JsonValue

MAX_TEACHER_BYTES = 64 * 1024**2


def json_value(value: object, depth: int = 0) -> JsonValue:
    if depth > 64:
        raise ValueError("Teacher evidence nesting exceeds explicit format bound")
    if value is None or type(value) in (str, bool, int):
        return cast(JsonValue, value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite evidence number")
        return value
    if type(value) is list:
        return [json_value(item, depth + 1) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Exact JSON string keys required")
        return {key: json_value(item, depth + 1) for key, item in value.items()}
    raise ValueError("Only complete finite JSON evidence is supported")


def _pairs(values: list[tuple[str, object]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate Teacher evidence field")
        result[key] = json_value(value)
    return result


def _constant(value: str) -> None:
    raise ValueError("Nonfinite Teacher evidence number")


def read_json(raw: str | bytes) -> JsonValue:
    if (
        type(raw) not in (str, bytes)
        or not 0
        < len(raw.encode("utf-8") if isinstance(raw, str) else raw)
        <= MAX_TEACHER_BYTES
    ):
        raise ValueError("Complete bounded Teacher JSON required")
    value: object = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    return json_value(value)


def json_text(value: object) -> str:
    return json.dumps(
        json_value(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def same_json(left: object, right: object) -> bool:
    return json_text(left) == json_text(right)


def object_value(value: JsonValue, reason: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(reason)
    return value


def array_value(value: JsonValue, reason: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError(reason)
    return value
