"""Frozen role token limits and complete-request measurements, never send permits."""

import hashlib
from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    field_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .evidence import EvidenceRef
from .validation import Contract, Identifier, NonEmptyText, Sha256

ContextRole = Literal["actor", "teacher"]


class ContextBudgetProfile(Contract):
    schema_version: Literal["context-budget-profile/1"] = "context-budget-profile/1"
    role: ContextRole
    model: NonEmptyText
    provider: Identifier
    routing_ref: EvidenceRef
    configuration_ref: EvidenceRef
    tokenizer_sha256: Sha256
    template_sha256: Sha256
    counting_method: Identifier
    precision: Literal["exact", "estimated_upper_bound"]
    bound_evidence_ref: EvidenceRef | None
    context_window: int = Field(ge=1, le=2147483647)
    output_reserve: int = Field(ge=1, le=2147483647)
    input_limit: int = Field(ge=1, le=2147483647)
    provider_input_limit: int | None = Field(ge=1, le=2147483647)
    soft_target: int = Field(ge=1, le=2147483647)
    uncounted_overhead: int = Field(ge=0, le=2147483647)
    paid: bool
    fee_scope_ref: EvidenceRef | None

    @model_validator(mode="after")
    def usable_frozen_limits(self) -> Self:
        for ref in (self.routing_ref, self.configuration_ref):
            if ref.visibility != "private" or ref.media_type != "application/json":
                raise ValueError(
                    "Frozen private routing and configuration JSON required"
                )
        if self.precision == "exact":
            if self.bound_evidence_ref is not None:
                raise ValueError("Exact counting does not borrow an estimated bound")
        elif self.bound_evidence_ref is None or (
            self.bound_evidence_ref.visibility,
            self.bound_evidence_ref.content_schema,
            self.bound_evidence_ref.media_type,
        ) != ("private", "context-counting-bound/1", "application/json"):
            raise ValueError(
                "Estimated counting requires its independently verified bound reference"
            )
        if self.paid != (self.fee_scope_ref is not None):
            raise ValueError("Only paid contexts require the original shared fee scope")
        if self.fee_scope_ref is not None and (
            self.fee_scope_ref.visibility != "private"
            or self.fee_scope_ref.content_schema != "budget-scope/1"
        ):
            raise ValueError("Original private BudgetScope reference required")
        if self.hard_limit <= 0 or self.soft_target > self.hard_limit:
            raise ValueError(
                "Positive input space and soft target within hard limit required"
            )
        return self

    @property
    def hard_limit(self) -> int:
        limits = (
            self.input_limit,
            self.context_window - self.output_reserve - self.uncounted_overhead,
        )
        return (
            min(*limits, self.provider_input_limit)
            if self.provider_input_limit is not None
            else min(limits)
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class TokenMeasurement(Contract):
    schema_version: Literal[
        "context-token-measurement/1", "context-token-measurement/2"
    ] = "context-token-measurement/1"
    role: ContextRole
    input_ref: EvidenceRef
    profile_sha256: Sha256
    policy_sha256: Sha256
    input_tokens: int = Field(ge=1, le=2147483647)
    upper_bound_tokens: int = Field(ge=1, le=2147483647)
    precision: Literal["exact", "estimated_upper_bound"]
    complete_request: Literal[True]
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    observation_tokens: int | None = Field(default=None, ge=0, le=2147483647)
    observation_body_sha256: Sha256 | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "context-token-measurement/1",
            ("observation_tokens", "observation_body_sha256"),
        )

    @field_validator("complete_request", mode="before")
    @classmethod
    def exact_complete_flag(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("Complete-request flag must be an actual bool")
        return value

    @model_validator(mode="after")
    def full_role_input(self) -> Self:
        old = self.schema_version == "context-token-measurement/1"
        actor_version_fields(
            self,
            old,
            ("observation_tokens", "observation_body_sha256"),
            record_name="Context count",
        )
        if not old and (
            self.role != "actor"
            or self.observation_tokens is None
            or self.observation_body_sha256 is None
            or self.precision != "exact"
        ):
            raise ValueError(
                "Body count v2 requires exact Actor body provenance, never Teacher projection"
            )
        if (
            self.input_ref.visibility != "private"
            or self.input_ref.content_schema != self.role + "-model-input/1"
        ):
            raise ValueError("Measurement must bind the original complete role input")
        if (
            self.input_ref.media_type != "application/json"
            or not 0
            < self.input_ref.size_bytes
            <= (8 if self.role == "actor" else 64) * 1024**2
        ):
            raise ValueError("Original bounded complete model input JSON required")
        if self.upper_bound_tokens < self.input_tokens or (
            self.precision == "exact" and self.upper_bound_tokens != self.input_tokens
        ):
            raise ValueError(
                "Exact count or conservative verified upper bound required"
            )
        return self


class CountedContextInput(Contract):
    """Measurement plus the original count facts, available after worker close."""

    schema_version: Literal["counted-context-input/1"] = "counted-context-input/1"
    measurement: TokenMeasurement
    evidence_ref: EvidenceRef

    @model_validator(mode="after")
    def original_count_facts(self) -> Self:
        if (
            self.evidence_ref.visibility,
            self.evidence_ref.content_schema,
            self.evidence_ref.media_type,
        ) != (
            "private",
            self.measurement.role + "-context-count-execution/1",
            "application/json",
        ) or not 0 < self.evidence_ref.size_bytes <= 256 * 1024:
            raise ValueError("Original bounded role count execution evidence required")
        return self
