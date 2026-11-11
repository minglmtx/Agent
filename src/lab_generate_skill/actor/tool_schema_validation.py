"""Fixed JSON Schema adapter with strict Python/JSON numbers, no coercion."""

from dataclasses import dataclass
from importlib import import_module
import math
from typing import Any

# jsonschema is a mandatory pinned dependency. Its distribution has no typing
# metadata; contain that untyped boundary here instead of weakening project checks.
_jsonschema = import_module("jsonschema")
_base = _jsonschema.Draft202012Validator


def _integer(checker: Any, value: object) -> bool:
    return type(value) is int


def _number(checker: Any, value: object) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


_validator = _jsonschema.validators.extend(
    _base,
    type_checker=_base.TYPE_CHECKER.redefine_many(
        {"integer": _integer, "number": _number}
    ),
)


@dataclass(frozen=True)
class ActorSchemaViolation:
    path: tuple[str | int, ...]
    keyword: str
    allowed: object
    message: str


def actor_schema_violations(
    schema: dict[str, Any], value: object
) -> tuple[ActorSchemaViolation, ...]:
    # Schemas are generated from the frozen local catalog; no external refs.
    result: list[ActorSchemaViolation] = []
    for error in _validator(schema).iter_errors(value):
        pending: list[Any] = [error]
        while pending and len(result) < 8:
            item = pending.pop(0)
            result.append(
                ActorSchemaViolation(
                    tuple(item.absolute_path),
                    str(item.validator),
                    item.validator_value,
                    str(item.message),
                )
            )
            pending[0:0] = list(item.context)
        if len(result) >= 8:
            break
    return tuple(result)
