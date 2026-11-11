"""Pinned configuration for one corrected-stage admission, never a permit."""

from typing import Any, Literal, Self
from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)
from .claims import SourceClaimBinding
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Identifier


class StageParentEvidence(Contract):
    run_ref: EvidenceRef
    trace_ref: EvidenceRef
    initialized_ref: EvidenceRef
    reset_refs: tuple[EvidenceRef, ...] = Field(min_length=2, max_length=2)
    resource_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def exact_private_evidence(self) -> Self:
        for reference, schema in (
            (self.run_ref, "run-journal-snapshot/2"),
            (self.trace_ref, "trace-journal-snapshot/1"),
            (self.initialized_ref, "initialized-task/1"),
            *((ref, "reset-receipt/1") for ref in self.reset_refs),
            *((ref, "resource-record/2") for ref in self.resource_refs),
        ):
            private_state_ref(reference, schema)
        if len(set(self.reset_refs)) != 2 or len(set(self.resource_refs)) != len(
            self.resource_refs
        ):
            raise ValueError("Parent evidence cannot duplicate reset/resource records")
        return self


class ClosedPreAttemptStageEvidence(Contract):
    """Retained facts for one failed Actor-only stage with no attempt or site."""

    schema_version: Literal["closed-pre-attempt-stage-evidence/1"] = (
        "closed-pre-attempt-stage-evidence/1"
    )
    claim_ref: EvidenceRef
    source_ref: EvidenceRef
    run_ref: EvidenceRef
    actor_resource_ref: EvidenceRef
    session_ref: EvidenceRef
    diagnostic_ref: EvidenceRef
    accounting_ref: EvidenceRef

    @model_validator(mode="after")
    def exact_evidence(self) -> Self:
        for reference, schema in (
            (self.claim_ref, "source-claim/1"),
            (self.source_ref, "execution-task-source/2"),
            (self.run_ref, "run-journal-snapshot/2"),
            (self.actor_resource_ref, "resource-record/2"),
            (self.session_ref, "evidence-session-snapshot/3"),
            (self.diagnostic_ref, "current-run-close/1"),
            (self.accounting_ref, "slurm-accounting-raw/1"),
        ):
            private_state_ref(reference, schema)
        return self


class StageValidationAuthorization(Contract):
    schema_version: Literal[
        "task-stage-validation-authorization/1",
        "task-stage-validation-authorization/2",
        "task-stage-validation-authorization/3",
        "task-stage-validation-authorization/4",
    ] = "task-stage-validation-authorization/1"
    authorization_id: Identifier
    binding: SourceClaimBinding
    parent_claim_ref: EvidenceRef
    parent_source_ref: EvidenceRef
    parent_evidence: StageParentEvidence
    stage_scope: Literal["corrected_actor_to_close"] = "corrected_actor_to_close"
    closed_prior_stage_refs: tuple[EvidenceRef, ...] = Field(default=(), max_length=128)

    @model_serializer(mode="wrap")
    def versioned_bytes(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.schema_version == "task-stage-validation-authorization/1":
            value.pop("closed_prior_stage_refs", None)
        return value

    @model_validator(mode="after")
    def original_refs(self) -> Self:
        private_state_ref(self.parent_claim_ref, "source-claim/1")
        private_state_ref(self.parent_source_ref, "execution-task-source/1")
        if (self.schema_version != "task-stage-validation-authorization/1") != bool(
            self.closed_prior_stage_refs
        ):
            raise ValueError(
                "Prior stage evidence requires explicit authorization/2, /3 or /4"
            )
        allowed = {"closed-pre-attempt-stage-evidence/1"}
        if self.schema_version in (
            "task-stage-validation-authorization/3",
            "task-stage-validation-authorization/4",
        ):
            allowed.add("closed-pre-registration-stage-evidence/1")
            if (
                self.schema_version == "task-stage-validation-authorization/3"
                and not any(
                    r.content_schema == "closed-pre-registration-stage-evidence/1"
                    for r in self.closed_prior_stage_refs
                )
            ):
                raise ValueError(
                    "Authorization/3 requires an explicit pre-registration review"
                )
        if self.schema_version == "task-stage-validation-authorization/4":
            allowed.add("ended-preparation-stage-evidence/1")
            if not any(
                r.content_schema == "ended-preparation-stage-evidence/1"
                for r in self.closed_prior_stage_refs
            ):
                raise ValueError(
                    "Authorization/4 requires an explicit ended-preparation review"
                )
        for reference in self.closed_prior_stage_refs:
            if reference.content_schema not in allowed:
                raise ValueError(
                    "Prior review differs from selected authorization version"
                )
            private_state_ref(reference, reference.content_schema)
        if len(set(self.closed_prior_stage_refs)) != len(self.closed_prior_stage_refs):
            raise ValueError("Prior stage review references must be unique")
        return self
