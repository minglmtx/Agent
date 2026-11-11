"""Original native SFT files and their complete immutable checkpoint snapshot."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator, field_validator
from .validation import Contract, Identifier, NonEmptyText, Sha256
from .training import TrainingPlan
from .release import ReleaseArtifact
from .evidence import EvidenceRef
from .lifecycle import ClosureReceipt, AllocationToken
from .process_identity import ProcessIdentity
from .state_scope import private_state_ref


class TrainingOutputPlan(Contract):
    schema_version: Literal["sft-output-plan/1"] = "sft-output-plan/1"
    training: TrainingPlan
    workspace_root: str
    output_root: str
    publication_root: str
    max_files: int = Field(ge=1, le=100000)
    max_file_bytes: int = Field(ge=1, le=2 * 1024**4)
    max_total_bytes: int = Field(ge=1, le=2 * 1024**4)

    @field_validator("workspace_root", "output_root", "publication_root")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        p = PurePosixPath(value)
        if (
            not p.is_absolute()
            or str(p) != value
            or ".." in p.parts
            or any(c in value for c in ("\0", "\\"))
            or len(value) > 4096
        ):
            raise ValueError("Canonical absolute original output paths required")
        return value

    @model_validator(mode="after")
    def original_roots(self) -> Self:
        w, s, p = (
            PurePosixPath(v)
            for v in (self.workspace_root, self.output_root, self.publication_root)
        )
        expected = (
            "sft-" + hashlib.sha256(self.training.training_id.encode()).hexdigest()
        )
        if (
            s.name != expected
            or s == w
            or p == w
            or not s.is_relative_to(w)
            or not p.is_relative_to(w)
            or s.is_relative_to(p)
            or p.is_relative_to(s)
        ):
            raise ValueError(
                "Distinct owned source/publication subtrees of trusted workspace required"
            )
        if self.max_file_bytes > self.max_total_bytes:
            raise ValueError("Individual file budget exceeds complete snapshot budget")
        return self


class NativeSFTEvaluation(Contract):
    step: int = Field(ge=0)
    epoch: int = Field(ge=0)
    loss: float = Field(allow_inf_nan=False)
    evaluation_kind: Literal["initial", "resume", "epoch"]


class NativeSFTSummary(Contract):
    complete: Literal[True]
    global_step: int = Field(ge=1)
    planned_optimizer_steps: int = Field(ge=1)
    epochs_visited: int = Field(ge=1)
    max_steps_limited: bool
    checkpoint_selection: NonEmptyText
    epoch_eval_metrics: tuple[NativeSFTEvaluation, ...] = Field(
        min_length=1, max_length=100000
    )
    initial_eval_loss: float = Field(allow_inf_nan=False)
    invocation_initial_eval_loss: float = Field(allow_inf_nan=False)
    final_eval_loss: float = Field(allow_inf_nan=False)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    elapsed_seconds_scope: NonEmptyText
    checkpoint_lineage_elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    checkpoint_lineage_elapsed_scope: NonEmptyText
    resumed_from_checkpoint: NonEmptyText | None
    peak_memory_gib: float = Field(ge=0, allow_inf_nan=False)
    train_rows: int = Field(ge=1)
    dev_rows: int = Field(ge=1)
    max_seq_length: int = Field(ge=1, le=16384)
    adapter: Literal["final_adapter"]


class NativeSFTOutcome(Contract):
    status: Literal["completed", "stopped"]
    optimizer_steps: int = Field(ge=1)
    planned_optimizer_steps: int = Field(ge=1)
    selected_checkpoint: str = Field(pattern=r"^checkpoint-[0-9]{6}$")
    contract_sha256: Sha256

    @model_validator(mode="after")
    def native_steps(self) -> Self:
        if (
            int(self.selected_checkpoint.removeprefix("checkpoint-"))
            != self.optimizer_steps
            or self.optimizer_steps > self.planned_optimizer_steps
            or (
                self.status == "completed"
                and self.optimizer_steps != self.planned_optimizer_steps
            )
        ):
            raise ValueError("Native complete marker/checkpoint/step outcome mismatch")
        return self


class NativeTrainingExecution(Contract):
    schema_version: Literal["sft-native-execution/1"] = "sft-native-execution/1"
    training_id: Identifier
    training_plan_ref: EvidenceRef
    dataset_ref: EvidenceRef
    training_release_ref: EvidenceRef
    installation_ref: EvidenceRef
    token: AllocationToken
    worker: ProcessIdentity
    contract_sha256: Sha256
    returned: Literal[True]
    source: ReleaseArtifact

    @model_validator(mode="after")
    def original_private_return(self) -> Self:
        for ref, schema in (
            (self.training_plan_ref, "training-plan/1"),
            (self.dataset_ref, "dataset-manifest/1"),
            (self.training_release_ref, "release-manifest/1"),
            (self.installation_ref, "release-installation/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.token.resource_kind != "trainer_model"
            or self.token.scope != "batch"
            or len(self.model_dump_json().encode()) > 8 * 1024**2
        ):
            raise ValueError("Original bounded trainer worker return evidence required")
        return self


def output_artifact_id(source: ReleaseArtifact) -> str:
    return "sft-output-" + hashlib.sha256(source.model_dump_json().encode()).hexdigest()


def require_training_closure(plan: TrainingOutputPlan, closure: ClosureReceipt) -> None:
    t, c = plan.training, ClosureReceipt.model_validate(closure)
    if (
        c.status != "closed"
        or c.primary_error is not None
        or c.cleanup_errors
        or (c.token.owner.run_id, c.token.owner.owner_id)
        != (t.dataset.operation.run_id, t.dataset.operation.owner_id)
        or c.token.scope != "batch"
        or c.token.resource_kind != "trainer_model"
        or any(r.visibility != "private" for r in c.evidence)
    ):
        raise ValueError(
            "Original complete trainer resource closure required, not a leader exit or label"
        )


class SFTCheckpoint(Contract):
    schema_version: Literal["sft-checkpoint/1"] = "sft-checkpoint/1"
    plan: TrainingOutputPlan
    dataset_ref: EvidenceRef
    source: ReleaseArtifact
    artifact: ReleaseArtifact
    native: NativeSFTOutcome
    closure: ClosureReceipt
    execution_ref: EvidenceRef

    @model_validator(mode="after")
    def complete_original_files(self) -> Self:
        p, t = self.plan, self.plan.training
        private_state_ref(self.dataset_ref, "dataset-manifest/1")
        private_state_ref(self.execution_ref, "sft-native-execution/1")
        if (
            self.source.root != p.output_root
            or self.artifact.files != self.source.files
            or self.artifact.artifact_id != output_artifact_id(self.source)
            or self.artifact.root
            != str(PurePosixPath(p.publication_root) / self.artifact.artifact_id)
        ):
            raise ValueError(
                "Snapshot must retain exact full original inventory and publication identity"
            )
        if (
            len(self.source.files) > p.max_files
            or sum(f.size_bytes for f in self.source.files) > p.max_total_bytes
            or any(
                f.executable or f.size_bytes > p.max_file_bytes
                for f in self.source.files
            )
        ):
            raise ValueError(
                "Complete native output exceeds original file/storage limits"
            )
        require_training_closure(p, self.closure)
        if len(self.model_dump_json().encode()) > 8 * 1024**2:
            raise ValueError(
                "Complete checkpoint metadata exceeds bound; files remain intact"
            )
        return self
