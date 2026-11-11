"""Content-addressed evidence descriptors and evaluator requirements.

These models describe bytes; they never read files or establish authenticity.
schema_version versions the descriptor; content_schema versions its payload.
Visibility is checked again by the consumer's input policy, not a sandbox.
"""

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .validation import Contract, Identifier, NonEmptyText, Sha256

Visibility = Literal["public", "teacher", "private"]


class EvidenceMetadata(Contract):
    """Metadata supplied to a store when persisting bytes, never credentials."""

    schema_version: Literal["evidence-metadata/1"] = "evidence-metadata/1"
    media_type: NonEmptyText
    content_schema: NonEmptyText
    visibility: Visibility
    producer: Identifier


class EvidenceRef(Contract):
    """Stable content identity plus location; relocation cannot change digest."""

    schema_version: Literal["evidence-ref/1"] = "evidence-ref/1"
    uri: NonEmptyText
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    media_type: NonEmptyText
    content_schema: NonEmptyText
    visibility: Visibility
    producer: Identifier

    @field_validator("uri")
    @classmethod
    def require_uri(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not parsed.scheme
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Evidence location needs a scheme and no credentials")
        if any(char.isspace() for char in value):
            raise ValueError("Evidence URI must not contain raw whitespace")
        return value


class EvidenceRequirement(Contract):
    """A required fact schema and its permitted visibility, named by the task."""

    schema_version: Literal["evidence-requirement/1"] = "evidence-requirement/1"
    name: Identifier
    content_schema: NonEmptyText
    visibility: Visibility


class EvidenceRequirements(Contract):
    """Capture preflight input; missing required facts produce unknown results."""

    schema_version: Literal["evidence-requirements/1"] = "evidence-requirements/1"
    facts: tuple[EvidenceRequirement, ...] = ()
    events: tuple[
        Literal["before_action", "after_action", "response", "download", "terminal"],
        ...,
    ] = ()

    @model_validator(mode="after")
    def distinct_requirements(self) -> Self:
        if len({fact.name for fact in self.facts}) != len(self.facts):
            raise ValueError("Evidence fact names must be unique")
        if len(set(self.events)) != len(self.events):
            raise ValueError("Evidence event requirements must be unique")
        return self
