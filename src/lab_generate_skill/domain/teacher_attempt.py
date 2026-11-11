"""Original Actor leaves used to produce a complete Teacher-permitted attempt.

These contracts never grant raw read, source or dispatch permission. The mandatory
source authority approves the exact original policy and source at both boundaries.
Private provenance stays outside the native model-visible view.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Identifier
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .lifecycle import OperationContext
from .teacher_scope import TeacherContextScope
from .teacher_source import TeacherAttemptSource, teacher_ref


class TeacherFeedbackPolicy(Contract):
    schema_version: Literal["teacher-feedback-policy/1"] = "teacher-feedback-policy/1"
    policy_id: Identifier
    authorization_ref: EvidenceRef
    check_names: tuple[Identifier, ...] = Field(max_length=10000)

    @model_validator(mode="after")
    def explicit_allowed_checks(self) -> Self:
        private_state_ref(self.authorization_ref, "teacher-feedback-authorization/1")
        if len(self.check_names) != len(set(self.check_names)):
            raise ValueError("Unique complete allowed feedback names required")
        if (
            self.authorization_ref.media_type != "application/json"
            or not 0 < self.authorization_ref.size_bytes <= 1024**2
        ):
            raise ValueError("Bounded original feedback authorization required")
        return self


class TeacherAttemptInput(Contract):
    schema_version: Literal["teacher-attempt-source-input/1"] = (
        "teacher-attempt-source-input/1"
    )
    scope: TeacherContextScope
    candidate_slot: int = Field(ge=0, le=6)
    actor_request_ref: EvidenceRef
    trace_ref: EvidenceRef
    evaluation_ref: EvidenceRef
    feedback: TeacherFeedbackPolicy
    operation: OperationContext

    @model_validator(mode="after")
    def exact_original_scope(self) -> Self:
        op = self.operation
        if (op.run_id, op.owner_id, op.mode) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            "execute",
        ) or any(
            v is not None for v in (op.attempt_id, op.allocation_id, op.recovery_ref)
        ):
            raise ValueError("Original run-level source command required")
        for ref, schemas, limit in (
            (
                self.actor_request_ref,
                ("actor-run-request/1", "actor-run-request/2"),
                16 * 1024**2,
            ),
            (self.trace_ref, ("interaction-trace/1",), 16 * 1024**2),
            (self.evaluation_ref, ("evaluation/1",), 2 * 1024**2),
        ):
            if ref.content_schema not in schemas:
                raise ValueError(
                    "Explicit original Actor/Trace/Evaluation schema required"
                )
            private_state_ref(ref, ref.content_schema)
            if ref.media_type != "application/json" or not 0 < ref.size_bytes <= limit:
                raise ValueError("Bounded original private source JSON required")
        return self


class TeacherAttemptReceipt(Contract):
    schema_version: Literal["teacher-attempt-source-receipt/1"] = (
        "teacher-attempt-source-receipt/1"
    )
    original: TeacherAttemptInput
    source: TeacherAttemptSource

    @model_validator(mode="after")
    def bind_original_leaves(self) -> Self:
        if (
            self.source.candidate_slot,
            self.source.actor_request_ref,
            self.source.trace_ref,
        ) != (
            self.original.candidate_slot,
            self.original.actor_request_ref,
            self.original.trace_ref,
        ):
            raise ValueError("Published attempt changed original source leaves")
        if len(self.model_dump_json().encode()) > 256 * 1024:
            raise ValueError("Bounded native attempt provenance required")
        return self


class PublishedTeacherAttempt(Contract):
    receipt_ref: EvidenceRef
    source: TeacherAttemptSource

    @model_validator(mode="after")
    def receipt_boundary(self) -> Self:
        private_state_ref(self.receipt_ref, "teacher-attempt-source-receipt/1")
        if (
            self.receipt_ref.media_type != "application/json"
            or not 0 < self.receipt_ref.size_bytes <= 256 * 1024
        ):
            raise ValueError("Bounded original attempt receipt required")
        teacher_ref(
            self.source.allowed_view_ref, "teacher-attempt-input/1", 64 * 1024**2
        )
        return self
