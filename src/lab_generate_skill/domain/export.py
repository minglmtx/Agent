"""Explicit source/review/qualification bindings; no inferred latest branch."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Identifier, NonEmptyText
from .dataset import DatasetKind, TrainingLabels
from .identity import TaskIdentity
from .evidence import EvidenceRef
from .execution import RunBinding
from .lifecycle import OperationContext
from .review import ReviewPlan
from .state_scope import private_state_ref


class ExportScope(Contract):
    schema_version: Literal["export-scope/1"] = "export-scope/1"
    scope_id: Identifier
    kind: DatasetKind
    release_ref: EvidenceRef
    split_ref: EvidenceRef
    allowed_tasks: tuple[TaskIdentity, ...] = Field(min_length=1, max_length=900)
    allowed_runs: tuple[RunBinding, ...] = Field(min_length=1, max_length=900)
    allowed_evaluation_scopes: tuple[
        Literal["benchmark", "local_derived", "engineering"], ...
    ] = Field(min_length=1, max_length=3)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def train_only(self) -> Self:
        private_state_ref(self.release_ref, "release-manifest/1")
        private_state_ref(self.split_ref, "data-split/1")
        if any(t.split != "train" for t in self.allowed_tasks) or len(
            set(t.model_dump_json() for t in self.allowed_tasks)
        ) != len(self.allowed_tasks):
            raise ValueError(
                "Export scope must explicitly name unique allowed train tasks"
            )
        if any(r.visibility != "private" for r in self.evidence_refs):
            raise ValueError("Actual source/phase/authorization evidence stays private")
        if len({r.model_dump_json() for r in self.allowed_runs}) != len(
            self.allowed_runs
        ) or any(r.release_ref != self.release_ref for r in self.allowed_runs):
            raise ValueError(
                "Unique explicitly allowed original runs of one release required"
            )
        if self.kind == "formal" and "engineering" in self.allowed_evaluation_scopes:
            raise ValueError("Engineering executions cannot enter formal training")
        return self


class ExportSource(Contract):
    example_id: Identifier
    legacy_id: Identifier
    review_ref: EvidenceRef
    qualification_ref: EvidenceRef
    review_read: ReviewPlan

    @model_validator(mode="after")
    def explicit_sources(self) -> Self:
        if self.example_id != self.legacy_id:
            raise ValueError("Explicit original id mapping required")
        private_state_ref(self.review_ref, "construction-review-receipt/1")
        private_state_ref(self.qualification_ref, "training-target-qualification/1")
        return self


class ExportPlan(Contract):
    schema_version: Literal["export-plan/1"] = "export-plan/1"
    export_id: Identifier
    kind: DatasetKind
    scope_ref: EvidenceRef
    split_ref: EvidenceRef
    release_ref: EvidenceRef
    sources: tuple[ExportSource, ...] = Field(min_length=1, max_length=900)
    seed: int = Field(ge=0, le=2147483647)
    validation_ratio: float = Field(gt=0, lt=1, allow_inf_nan=False)
    operation: OperationContext

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        private_state_ref(self.scope_ref, "export-scope/1")
        private_state_ref(self.split_ref, "data-split/1")
        private_state_ref(self.release_ref, "release-manifest/1")
        if len({s.example_id for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate export source identity")
        for source in self.sources:
            op = source.review_read.operation
            if source.review_read.run.release_ref != self.release_ref:
                raise ValueError("Original release must be explicit")
            if op.deadline > self.operation.deadline:
                raise ValueError("Export reads cannot extend the original deadline")
        if (
            self.operation.attempt_id is not None
            or self.operation.allocation_id is not None
            or self.operation.recovery_ref is not None
            or self.operation.mode != "execute"
        ):
            raise ValueError(
                "Export uses an explicit original run-level metadata operation"
            )
        if len(self.model_dump_json().encode()) > 4 * 1024**2:
            raise ValueError("Complete export plan exceeds bound")
        return self


class TrainingTargetQualification(Contract):
    schema_version: Literal["training-target-qualification/1"] = (
        "training-target-qualification/1"
    )
    kind: DatasetKind
    run: RunBinding
    task: TaskIdentity
    scope_ref: EvidenceRef
    review_ref: EvidenceRef
    sealed_evidence_ref: EvidenceRef
    selected_evaluation_ref: EvidenceRef | None
    target_skill_ref: EvidenceRef | None
    retrieval_ref: EvidenceRef
    labels: TrainingLabels
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def private_provenance(self) -> Self:
        for ref, schema in (
            (self.scope_ref, "export-scope/1"),
            (self.review_ref, "construction-review-receipt/1"),
            (self.sealed_evidence_ref, "construction-progress/1"),
            (self.retrieval_ref, "retrieval-result/1"),
        ):
            private_state_ref(ref, schema)
        if self.task.split != "train" or any(
            r.visibility != "private" for r in self.evidence_refs
        ):
            raise ValueError(
                "Qualification needs original train/private source evidence"
            )
        return self


class ExportAdmission(Contract):
    status: Literal["eligible", "ineligible"]
    reason_code: Identifier
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=128)


class ExportDecision(Contract):
    example_id: Identifier
    status: Literal[
        "exported", "ineligible", "no_positive_target", "review_unconfirmed"
    ]
    reason_code: Identifier
    review_ref: EvidenceRef


class ExportReceipt(Contract):
    schema_version: Literal["export-receipt/1"] = "export-receipt/1"
    export_plan_ref: EvidenceRef
    kind: DatasetKind
    dataset_ref: EvidenceRef | None
    example_count: int = Field(ge=0, le=900)
    status: Literal["empty", "train_validation_ready", "awaiting_goal_groups"]
    decisions: tuple[ExportDecision, ...] = Field(min_length=1, max_length=900)

    @model_validator(mode="after")
    def explicit_empty(self) -> Self:
        private_state_ref(self.export_plan_ref, "export-plan/1")
        count = sum(d.status == "exported" for d in self.decisions)
        if (
            count != self.example_count
            or (count == 0) != (self.dataset_ref is None)
            or (self.status == "empty") != (count == 0)
        ):
            raise ValueError(
                "Exact exported count and explicit empty/no-dataset result required"
            )
        if len({d.example_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("Every source requires exactly one explicit decision")
        if self.dataset_ref is not None:
            private_state_ref(self.dataset_ref, "dataset-manifest/1")
        return self


class DatasetLoadPlan(Contract):
    schema_version: Literal["dataset-load-plan/1"] = "dataset-load-plan/1"
    export_receipt_ref: EvidenceRef
    expected_kind: DatasetKind
    purpose: Literal["inspect", "sft"]
    sources: tuple[ExportSource, ...] = Field(min_length=1, max_length=900)
    operation: OperationContext

    @model_validator(mode="after")
    def explicit_consumer(self) -> Self:
        private_state_ref(self.export_receipt_ref, "export-receipt/1")
        if self.purpose == "sft" and self.expected_kind != "formal":
            raise ValueError("Fixture artifacts cannot enter parameter training")
        return self
