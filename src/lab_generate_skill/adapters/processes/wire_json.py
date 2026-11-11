"""Shared process-boundary JSON decoding; reject duplicate/nonfinite fields."""

import json
from decimal import Decimal
from typing import Any


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("Nonfinite JSON number")


def json_object(raw: bytes, *, exact_numbers: bool = False) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise TypeError("Wire JSON must be exact bytes")
    result = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_constant,
        parse_float=Decimal if exact_numbers else float,
    )
    if not isinstance(result, dict):
        raise ValueError("Wire document must be an object")
    return result
