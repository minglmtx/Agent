"""Same-release construction review; evidence consistency is not training admission.

The first contract checks original judgments only. Cross-release rejudgment needs
its own two-process reconstruction contract and is explicitly rejected here.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .construction import SelectionResult
from .evidence import EvidenceRef
from .evaluation import Evaluation
from .execution import RunBinding
from .lifecycle import OperationContext
from .state_scope import private_state_ref
from .task_teacher import PublishedTaskTeacherAttempt
from .teacher_assembly import PublishedTeacherRevisionAssembly
from .validation import Contract, Identifier


class ReviewTask(Contract):
    published: PublishedTaskTeacherAttempt
    operation: OperationContext


class ReviewTeacher(Contract):
    published: PublishedTeacherRevisionAssembly
    operation: OperationContext


class ReviewPlan(Contract):
    schema_version: Literal["construction-review-plan/1"] = "construction-review-plan/1"
    review_id: Identifier
    run: RunBinding
    original_run_plan_ref: EvidenceRef
    sealed_evidence_ref: EvidenceRef
    original_execution_release: EvidenceRef
    judgment_release: EvidenceRef
    selection: SelectionResult
    selected_evaluation_ref: EvidenceRef | None
    tasks: tuple[ReviewTask, ...] = Field(min_length=5, max_length=7)
    teachers: tuple[ReviewTeacher, ...] = Field(min_length=1, max_length=3)
    operation: OperationContext

    @model_validator(mode="after")
    def original_complete_scope(self) -> Self:
        if (
            self.original_run_plan_ref != self.run.plan_ref
            or self.original_execution_release != self.run.release_ref
            or self.judgment_release != self.original_execution_release
        ):
            raise ValueError(
                "Original run/release required; cross-release rejudgment is unsupported"
            )
        private_state_ref(self.sealed_evidence_ref, "construction-progress/1")
        if (
            self.sealed_evidence_ref.media_type != "application/json"
            or not 0 < self.sealed_evidence_ref.size_bytes <= 8 * 1024**2
        ):
            raise ValueError("Complete canonical sealed construction required")
        if (self.selection.status == "accepted") != (
            self.selected_evaluation_ref is not None
        ):
            raise ValueError("Select the exact original accepted evaluation branch")
        if self.selected_evaluation_ref is not None:
            private_state_ref(self.selected_evaluation_ref, "evaluation/1")
        if len(self.tasks) != 4 + len(self.teachers):
            raise ValueError("Every original and revised attempt must be reviewed")
        sources = tuple(t.published.part.source for t in self.tasks)
        if tuple(s.candidate_slot for s in sources) != tuple(
            range(len(self.tasks))
        ) or len({s.attempt_id for s in sources}) != len(sources):
            raise ValueError(
                "Complete ordered unique original attempt history required"
            )
        revisions = tuple(t.published.bound.plan.revision for t in self.teachers)
        if tuple(t.teacher_round for t in revisions) != tuple(
            range(1, len(revisions) + 1)
        ) or len({t.request_id for t in revisions}) != len(revisions):
            raise ValueError(
                "Complete ordered unique original Teacher history required"
            )
        owner = self.run.owner
        operations: dict[str, OperationContext] = {}
        for op in (
            self.operation,
            *(t.operation for t in self.tasks),
            *(t.operation for t in self.teachers),
        ):
            if (
                op.run_id,
                op.owner_id,
                op.attempt_id,
                op.allocation_id,
                op.recovery_ref,
            ) != (owner.run_id, owner.owner_id, None, None, None):
                raise ValueError("Review requires original run-level readonly scope")
            if (
                op.deadline > self.operation.deadline
                or op.cancellation_ref != self.operation.cancellation_ref
            ):
                raise ValueError(
                    "Review leaf reads cannot extend its deadline or drop cancellation"
                )
            if op.operation_id in operations and operations[op.operation_id] != op:
                raise ValueError(
                    "One review identity cannot bind different read metadata"
                )
            operations[op.operation_id] = op
        if any(t.operation.mode != "cleanup" for t in self.tasks) or any(
            t.operation.mode != "cleanup" for t in self.teachers
        ):
            raise ValueError(
                "Original source and Teacher reads require bounded parent cleanup"
            )
        if len(self.model_dump_json().encode()) > 2 * 1024**2:
            raise ValueError("Review plan exceeds complete metadata bound")
        return self


class ReviewFinding(Contract):
    attempt_id: Identifier
    candidate_slot: int = Field(ge=0, le=6)
    original_evaluation_ref: EvidenceRef
    execution_ref: EvidenceRef
    reset_ref: EvidenceRef
    reproduced: Evaluation
    matches_recorded: bool


class ReviewReceipt(Contract):
    schema_version: Literal["construction-review-receipt/1"] = (
        "construction-review-receipt/1"
    )
    plan: ReviewPlan
    findings: tuple[ReviewFinding, ...] = Field(min_length=5, max_length=7)
    status: Literal["verified", "inconsistent", "insufficient_evidence"]
    selected_skill_ref: EvidenceRef | None
    training_admission: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def evidence_result_only(self) -> Self:
        expected = (
            "insufficient_evidence"
            if any(f.reproduced.status == "unknown" for f in self.findings)
            else (
                "verified"
                if all(f.matches_recorded for f in self.findings)
                else "inconsistent"
            )
        )
        if self.status != expected or tuple(
            (f.attempt_id, f.candidate_slot) for f in self.findings
        ) != tuple(
            (t.published.part.source.attempt_id, i)
            for i, t in enumerate(self.plan.tasks)
        ):
            raise ValueError(
                "Review outcome must preserve every original attempt and judgment"
            )
        needs_skill = (
            self.status == "verified" and self.plan.selection.status == "accepted"
        )
        if needs_skill != (self.selected_skill_ref is not None):
            raise ValueError(
                "Only a verified accepted original choice has a target reference"
            )
        if self.selected_skill_ref is not None and (
            self.selected_skill_ref.visibility,
            self.selected_skill_ref.content_schema,
            self.selected_skill_ref.media_type,
        ) != ("public", "compact-skill/1", "application/json"):
            raise ValueError("Original public selected skill required")
        if len(self.model_dump_json().encode()) > 8 * 1024**2:
            raise ValueError(
                "Complete review metadata exceeds bound; never truncate findings"
            )
        return self
