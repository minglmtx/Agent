"""Explicit task intent variants; construction wire bytes stay unchanged.

Execution has a frozen policy/input pair and no generated candidate slot on its
wire. Neither intent is permission; live source/claim/resource gates remain.
"""

from typing import Any, Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .execution import AttemptBinding
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Sha256


class TaskAttemptIntent(Contract):
    schema_version: Literal[
        "construction-attempt-intent/1", "execution-task-intent/1"
    ] = "construction-attempt-intent/1"
    binding: AttemptBinding
    candidate_slot: int = Field(default=0, ge=0, le=6)
    skill_digest: Sha256
    public_context_ref: EvidenceRef
    execution_policy_ref: EvidenceRef | None = None
    execution_inputs_ref: EvidenceRef | None = None

    @property
    def source_kind(self) -> Literal["construction", "execution"]:
        return (
            "construction"
            if self.schema_version == "construction-attempt-intent/1"
            else "execution"
        )

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.source_kind == "construction":
            data.pop("execution_policy_ref", None)
            data.pop("execution_inputs_ref", None)
        else:
            data.pop("candidate_slot", None)
        return data

    @model_validator(mode="after")
    def exact_variant(self) -> Self:
        if self.source_kind == "construction":
            if "candidate_slot" not in self.model_fields_set or any(
                k in self.model_fields_set
                for k in ("execution_policy_ref", "execution_inputs_ref")
            ):
                raise ValueError(
                    "Original construction slot required; execution fields forbidden"
                )
        else:
            if (
                "candidate_slot" in self.model_fields_set
                or self.execution_policy_ref is None
                or self.execution_inputs_ref is None
            ):
                raise ValueError(
                    "Execution binds explicit policy/inputs, never a generated candidate slot"
                )
            if (
                self.execution_policy_ref.visibility != "private"
                or self.execution_inputs_ref.visibility != "private"
            ):
                raise ValueError("Execution policy and source inputs remain private")
            if (
                self.execution_policy_ref.content_schema
                != "engineering-execution-policy/3"
                or self.execution_inputs_ref.content_schema != "execution-task-inputs/1"
            ):
                raise ValueError(
                    "Explicit current execution policy/source inputs required"
                )
            if (
                self.public_context_ref.visibility,
                self.public_context_ref.content_schema,
            ) != ("public", "public-construction-context/1"):
                raise ValueError(
                    "Execution needs the exact allowed public source context"
                )
        return self
