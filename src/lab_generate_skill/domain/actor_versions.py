"""Versioned call-record additions with byte-identical canonical historical v1.

The historical helper names remain stable for original Actor consumers.
"""

from typing import Any, cast
from pydantic import BaseModel, SerializerFunctionWrapHandler


def actor_version_fields(
    value: BaseModel, old: bool, fields: tuple[str, ...], *, record_name: str = "Actor"
) -> None:
    # Do not use before/wrap input validators: this runtime loses strict JSON
    # tuple/datetime semantics there. fields_set survives instance revalidation
    # and distinguishes explicit null fields from internal schema defaults.
    if old and any(name in value.model_fields_set for name in fields):
        raise ValueError(
            f"{record_name} v1 cannot carry v2 fields, including null values"
        )


def actor_version_output(
    value: object,
    handler: SerializerFunctionWrapHandler,
    old: bool,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    result = cast(dict[str, Any], handler(value))
    if old:
        for name in fields:
            result.pop(name, None)
    return result
