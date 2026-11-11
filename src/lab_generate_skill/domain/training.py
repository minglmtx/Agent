"""Frozen original SFT settings and source-bound results; no implicit permission."""

from typing import Literal, Self
from datetime import datetime
import hashlib
from pydantic import Field, model_validator
from .validation import Contract, Identifier, Sha256
from .export import DatasetLoadPlan
from .evidence import EvidenceRef
from .release import ReleaseArtifact
from .state_scope import private_state_ref
from .lifecycle import OperationContext


class TrainingSpec(Contract):
    schema_version: Literal["training-spec/1"] = "training-spec/1"
    max_seq_length: int = Field(default=16384, ge=1, le=16384)
    epochs: int = Field(default=3, ge=1, le=100)
    per_device_batch_size: int = Field(default=1, ge=1, le=64)
    gradient_accumulation_steps: int = Field(default=16, ge=1, le=4096)
    learning_rate: float = Field(default=2e-4, gt=0, le=1, allow_inf_nan=False)
    weight_decay: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    warmup_ratio: float = Field(default=0.03, ge=0, le=1, allow_inf_nan=False)
    max_grad_norm: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    lora_r: int = Field(default=16, ge=1, le=1024)
    lora_alpha: int = Field(default=32, ge=1, le=4096)
    lora_dropout: float = Field(default=0.05, ge=0, lt=1, allow_inf_nan=False)
    seed: int = Field(default=42, ge=0, le=2147483647)
    save_steps: int = Field(default=50, ge=1)
    log_steps: int = Field(default=5, ge=1)
    max_steps: int | None = Field(default=None, ge=1)
    train_limit: int | None = Field(default=None, ge=1)
    dev_limit: int | None = Field(default=None, ge=1)
    resume: bool = False


class TrainingPlan(Contract):
    schema_version: Literal["training-plan/1"] = "training-plan/1"
    training_id: Identifier
    dataset: DatasetLoadPlan
    training_release_ref: EvidenceRef
    phase_authorization_ref: EvidenceRef
    model: ReleaseArtifact
    spec: TrainingSpec
    cleanup_seconds: int = Field(default=60, ge=1, le=300)

    def cleanup(
        self, stage: Literal["result", "backend-result", "backend-abort"], now: datetime
    ) -> OperationContext:
        digest = hashlib.sha256(
            (self.training_id + ":" + self.dataset.operation.operation_id).encode()
        ).hexdigest()
        return self.dataset.operation.cleanup(
            "sft-" + stage + "-" + digest, now=now, seconds=self.cleanup_seconds
        )

    @model_validator(mode="after")
    def qualified_input_only(self) -> Self:
        if (self.dataset.expected_kind, self.dataset.purpose) != ("formal", "sft"):
            raise ValueError(
                "Parameter training requires the original formal SFT consumer"
            )
        op = self.dataset.operation
        if op.mode != "execute" or any(
            v is not None for v in (op.attempt_id, op.allocation_id, op.recovery_ref)
        ):
            raise ValueError(
                "Training requires an explicit run-level execute operation"
            )
        private_state_ref(self.training_release_ref, "release-manifest/1")
        private_state_ref(self.phase_authorization_ref, "training-authorization/1")
        if len(self.model_dump_json().encode()) > 8 * 1024**2:
            raise ValueError("Complete training plan exceeds metadata bound")
        return self


class TrainingRunResult(Contract):
    schema_version: Literal["training-run-result/1"] = "training-run-result/1"
    training_id: Identifier
    dataset_ref: EvidenceRef
    training_release_ref: EvidenceRef
    contract_sha256: Sha256
    status: Literal["completed", "stopped"]
    optimizer_steps: int = Field(ge=0)
    planned_optimizer_steps: int = Field(ge=1)
    checkpoint_ref: EvidenceRef
    runtime_evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def actual_result_only(self) -> Self:
        private_state_ref(self.dataset_ref, "dataset-manifest/1")
        private_state_ref(self.training_release_ref, "release-manifest/1")
        private_state_ref(self.checkpoint_ref, "sft-checkpoint/1")
        if self.optimizer_steps > self.planned_optimizer_steps or (
            self.status == "completed"
            and self.optimizer_steps != self.planned_optimizer_steps
        ):
            raise ValueError(
                "Completion requires every original planned optimizer update"
            )
        if any(r.visibility != "private" for r in self.runtime_evidence_refs):
            raise ValueError("Training runtime/source evidence remains private")
        return self


class TrainingReceipt(Contract):
    schema_version: Literal["training-receipt/1"] = "training-receipt/1"
    plan_ref: EvidenceRef
    result_ref: EvidenceRef
    result: TrainingRunResult

    @model_validator(mode="after")
    def source_refs(self) -> Self:
        private_state_ref(self.plan_ref, "training-plan/1")
        private_state_ref(self.result_ref, "training-run-result/1")
        return self
