"""Explicit approved attempt views and original construction source provenance.

Teacher visibility is a storage boundary, not an authorization grant. Original
source authority must verify the actual trace/feedback and all registered refs.
"""

from typing import Any, Literal, Self
from pydantic import (
    Field,
    JsonValue,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .validation import Contract, Identifier
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .teacher_scope import TeacherContextScope
from .context_projection import TeacherContextSource
from .state_scope import private_state_ref
from .teacher_json import json_value, MAX_TEACHER_BYTES


def teacher_ref(
    ref: EvidenceRef, schema: str, limit: int, media: str = "application/json"
) -> None:
    if (ref.visibility, ref.content_schema, ref.media_type) != (
        "teacher",
        schema,
        media,
    ) or not 0 < ref.size_bytes <= limit:
        raise ValueError(
            "Complete bounded original teacher-visible " + schema + " required"
        )


class TeacherAttemptView(Contract):
    schema_version: Literal["teacher-attempt-input/1"] = "teacher-attempt-input/1"
    scope: TeacherContextScope
    attempt_id: Identifier
    candidate_slot: int = Field(ge=0, le=6)
    native: dict[str, JsonValue]

    @model_validator(mode="after")
    def full_native(self) -> Self:
        json_value(self.native)
        if not {
            "skill",
            "success",
            "steps",
            "reward",
            "trajectory",
            "evaluator_feedback",
        } <= set(self.native):
            raise ValueError("Complete original allowed attempt fields required")
        if not isinstance(self.native["trajectory"], list):
            raise ValueError("Complete original ordered trajectory required")
        if len(self.model_dump_json().encode()) > MAX_TEACHER_BYTES:
            raise ValueError("Complete approved attempt exceeds byte boundary")
        return self


class TeacherAttemptSource(Contract):
    attempt_id: Identifier
    candidate_slot: int = Field(ge=0, le=6)
    allowed_view_ref: EvidenceRef
    actor_request_ref: EvidenceRef
    trace_ref: EvidenceRef

    @model_validator(mode="after")
    def explicit_originals(self) -> Self:
        teacher_ref(self.allowed_view_ref, "teacher-attempt-input/1", MAX_TEACHER_BYTES)
        if self.actor_request_ref.content_schema not in (
            "actor-run-request/1",
            "actor-run-request/2",
        ):
            raise ValueError("Original versioned Actor request required")
        private_state_ref(self.actor_request_ref, self.actor_request_ref.content_schema)
        private_state_ref(self.trace_ref, "interaction-trace/1")
        for ref in (self.actor_request_ref, self.trace_ref):
            if (
                ref.media_type != "application/json"
                or not 0 < ref.size_bytes <= 16 * 1024**2
            ):
                raise ValueError("Bounded original Actor request/trace JSON required")
        return self


class TeacherSourceBindings(Contract):
    schema_version: Literal[
        "teacher-source-bindings/1", "teacher-source-bindings/2"
    ] = "teacher-source-bindings/1"
    request_id: Identifier
    operation: OperationContext
    teacher_round: int = Field(ge=1, le=3)
    instructions_ref: EvidenceRef
    attempts: tuple[TeacherAttemptSource, ...] = Field(min_length=4, max_length=6)
    task_receipt_refs: tuple[EvidenceRef, ...] | None = Field(
        default=None, min_length=4, max_length=6
    )

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.schema_version == "teacher-source-bindings/1":
            result.pop("task_receipt_refs", None)
        return result

    @model_validator(mode="after")
    def original_task_command(self) -> Self:
        if self.schema_version == "teacher-source-bindings/1":
            if "task_receipt_refs" in self.model_fields_set:
                raise ValueError(
                    "Native-only source v1 forbids task receipt fields, including null"
                )
        else:
            refs = self.task_receipt_refs
            if (
                refs is None
                or len(refs) != len(self.attempts)
                or len(set(refs)) != len(refs)
            ):
                raise ValueError(
                    "Task-backed source v2 requires every distinct original task receipt"
                )
            for ref in refs:
                private_state_ref(ref, "task-teacher-receipt/1")
                if (
                    ref.media_type != "application/json"
                    or not 0 < ref.size_bytes <= 512 * 1024
                ):
                    raise ValueError(
                        "Bounded original private task receipt JSON required"
                    )
        op = self.operation
        if op.mode != "execute" or any(
            v is not None for v in (op.attempt_id, op.allocation_id, op.recovery_ref)
        ):
            raise ValueError(
                "Teacher source requires its original run-level execute command"
            )
        teacher_ref(
            self.instructions_ref, "teacher-instructions/1", 256 * 1024, "text/plain"
        )
        if len({a.attempt_id for a in self.attempts}) != len(self.attempts) or len(
            {a.candidate_slot for a in self.attempts}
        ) != len(self.attempts):
            raise ValueError("All distinct original attempts in order required")
        return self


class TeacherSourceReceipt(Contract):
    schema_version: Literal["teacher-source-receipt/1"] = "teacher-source-receipt/1"
    progress_ref: EvidenceRef
    bindings: TeacherSourceBindings
    source: TeacherContextSource

    @model_validator(mode="after")
    def immutable_history(self) -> Self:
        private_state_ref(self.progress_ref, "construction-progress/1")
        if (
            self.progress_ref.media_type != "application/json"
            or not 0 < self.progress_ref.size_bytes <= 8 * 1024**2
        ):
            raise ValueError("Complete bounded original construction progress required")
        if self.source.teacher_round != self.bindings.teacher_round or not isinstance(
            self.source.scope, TeacherContextScope
        ):
            raise ValueError("Teacher source must retain its original task scope/round")
        if len(self.model_dump_json().encode()) > 256 * 1024:
            raise ValueError("Teacher source provenance exceeds metadata boundary")
        return self


class PublishedTeacherSource(Contract):
    receipt_ref: EvidenceRef
    source: TeacherContextSource

    @model_validator(mode="after")
    def original_receipt(self) -> Self:
        private_state_ref(self.receipt_ref, "teacher-source-receipt/1")
        if (
            self.receipt_ref.media_type != "application/json"
            or not 0 < self.receipt_ref.size_bytes <= 256 * 1024
        ):
            raise ValueError("Bounded original source receipt required")
        return self
