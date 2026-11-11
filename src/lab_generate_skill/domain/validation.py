"""Boundary validation primitives; no business policy or infrastructure I/O.

Python callers supply exact field/container types. Process boundaries use
model_validate_json(), which accepts JSON arrays for immutable tuple fields.
Unknown fields and schema versions are rejected, not silently migrated.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    ),
]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class Contract(BaseModel):
    """Immutable boundary data; subclasses declare a literal schema_version.

    Use validation for untrusted input. Pydantic model_construct/model_copy(update)
    are trusted escape hatches and must not be used to ingest external records.
    """

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
    )
