"""Separate public model inputs from trusted task preparation references.

PublicTask is built directly from approved public fields, never by deleting
private keys from TaskBinding. No private reference is present in its schema.
"""

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .evidence import EvidenceRef
from .identity import TaskIdentity
from .validation import Contract, Identifier, NonEmptyText


class PublicTask(Contract):
    """Input to browser/Actor; contains only the publicly declared task."""

    schema_version: Literal["public-task/1"] = "public-task/1"
    identity: TaskIdentity
    goal: NonEmptyText
    start_url: NonEmptyText
    allowed_actions: tuple[Identifier, ...] = Field(min_length=1)
    output_requirements: tuple[NonEmptyText, ...] = ()

    @field_validator("start_url")
    @classmethod
    def public_start_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(char.isspace() for char in value)
        ):
            raise ValueError("Public start URL must be HTTP(S) without credentials")
        return value

    @field_validator("allowed_actions")
    @classmethod
    def distinct_actions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Allowed action names must be unique")
        return value


class TaskBinding(Contract):
    """Trusted assembly input; never serialize this object as a model prompt."""

    schema_version: Literal["task-binding/1"] = "task-binding/1"
    identity: TaskIdentity
    registration_id: Identifier
    public_task_ref: EvidenceRef
    private_spec_ref: EvidenceRef
    baseline_ref: EvidenceRef

    @model_validator(mode="after")
    def require_separate_views(self) -> Self:
        if self.public_task_ref.visibility != "public":
            raise ValueError("Public task reference must be public")
        if self.public_task_ref.content_schema != "public-task/1":
            raise ValueError("Public task reference has an unsupported payload schema")
        if (
            self.private_spec_ref.visibility != "private"
            or self.baseline_ref.visibility != "private"
        ):
            raise ValueError(
                "Private initialization and baseline references stay private"
            )
        return self
