"""Original Teacher call assembly command and immutable publication receipt.

No model/fee/dispatch permission. Source, count and original admission are checked
again by original Teacher/send/ledger boundaries. This only freezes metadata and
registers the original construction call once.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .budget import BudgetScope, Money
from .context_preparation import ContextPreparationRequest, PreparedContextRef
from .context_projection import TeacherContextSource
from .teacher_scope import TeacherContextScope
from .teacher_source import PublishedTeacherSource
from .model_request import ModelSendLimits, check_model_cleanup
from .lifecycle import OperationContext
from .construction import CallPlanned
from .teacher_revision import BoundTeacherRevisionPlan
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class TeacherRevisionAssemblyInput(Contract):
    schema_version: Literal["teacher-revision-assembly-input/1"] = (
        "teacher-revision-assembly-input/1"
    )
    source: PublishedTeacherSource
    preparation: ContextPreparationRequest
    prepared: PreparedContextRef
    budget: BudgetScope
    ceiling: Money
    limits: ModelSendLimits
    reserve_operation: OperationContext
    settlement_operation: OperationContext
    reasoning_accounting: Literal["completion_includes_reasoning", "separate_reasoning"]

    @model_validator(mode="after")
    def accepted_original_inputs(self) -> Self:
        request = self.preparation
        if (
            not isinstance(request.source, TeacherContextSource)
            or not isinstance(request.scope, TeacherContextScope)
            or request.schema_version != "context-preparation-request/2"
            or request.source != self.source.source
        ):
            raise ValueError("Original task-level Teacher source/preparation required")
        if (
            self.prepared.outcome != "prepared"
            or self.prepared.selected_input_ref is None
        ):
            raise ValueError(
                "Only an accepted original complete counted input can be assembled"
            )
        if self.reserve_operation.mode != "execute" or (
            self.reserve_operation.run_id,
            self.reserve_operation.owner_id,
            self.reserve_operation.attempt_id,
            self.reserve_operation.allocation_id,
            self.reserve_operation.recovery_ref,
        ) != (request.operation.run_id, request.operation.owner_id, None, None, None):
            raise ValueError("Reserve metadata must retain original run-level scope")
        check_model_cleanup(request.operation, self.settlement_operation)
        if (
            len(
                {
                    self.reserve_operation.operation_id,
                    request.operation.operation_id,
                    self.settlement_operation.operation_id,
                }
            )
            != 3
        ):
            raise ValueError("Reserve/send/settlement identities must be distinct")
        if self.ceiling.units <= 0 or self.ceiling.units > self.budget.ceiling.units:
            raise ValueError("Original positive conservative fee ceiling required")
        if len(self.model_dump_json().encode()) > 2 * 1024**2:
            raise ValueError("Teacher assembly metadata exceeds original bound")
        return self


class TeacherRevisionAssemblyReceipt(Contract):
    schema_version: Literal["teacher-revision-assembly/1"] = (
        "teacher-revision-assembly/1"
    )
    input_ref: EvidenceRef
    source_progress_ref: EvidenceRef
    plan_ref: EvidenceRef
    event: CallPlanned
    registered_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def original_private_records(self) -> Self:
        for ref, schema, limit in (
            (self.input_ref, "teacher-revision-assembly-input/1", 2 * 1024**2),
            (self.source_progress_ref, "construction-progress/1", 8 * 1024**2),
            (self.plan_ref, "teacher-revision-plan/1", 2 * 1024**2),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or not 0 < ref.size_bytes <= limit:
                raise ValueError("Bounded complete original assembly record required")
        if (
            self.event.call.role != "teacher"
            or len(self.model_dump_json().encode()) > 256 * 1024
        ):
            raise ValueError("Original Teacher call/receipt boundary required")
        return self


class PublishedTeacherRevisionAssembly(Contract):
    receipt_ref: EvidenceRef
    bound: BoundTeacherRevisionPlan

    @model_validator(mode="after")
    def immutable_receipt(self) -> Self:
        private_state_ref(self.receipt_ref, "teacher-revision-assembly/1")
        if (
            self.receipt_ref.media_type != "application/json"
            or not 0 < self.receipt_ref.size_bytes <= 256 * 1024
        ):
            raise ValueError("Original bounded assembly receipt required")
        return self
