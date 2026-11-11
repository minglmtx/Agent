"""Unified original-source dataset -> explicit phase -> one original SFT trainer."""

from dataclasses import dataclass
from lab_generate_skill.domain.training import (
    TrainingPlan,
    TrainingRunResult,
    TrainingReceipt,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.training import TrainingAuthority, Trainer
from lab_generate_skill.ports.lifecycle import Clock
from lab_generate_skill.policies.training_admission import require_training_dataset
from lab_generate_skill.policies.training_metadata import (
    training_metadata as training_metadata,
)
from .export_targets import ExportDeps
from .dataset_reader import load_dataset
from .context_evidence import publish_raw


@dataclass(frozen=True)
class TrainingDeps:
    dataset: ExportDeps
    authority: TrainingAuthority
    trainer: Trainer
    clock: Clock

    def __post_init__(self) -> None:
        if any(
            not callable(getattr(p, name, None))
            for p, name in (
                (self.authority, "verify"),
                (self.authority, "verify_result"),
                (self.trainer, "train"),
                (self.clock, "utcnow"),
            )
        ):
            raise ValueError(
                "Explicit source/phase/runtime authority and original trainer required"
            )


class TrainingUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: TrainingPlan,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
        result: TrainingRunResult | None,
    ) -> None:
        self.plan, self.phase, self.primary, self.retained, self.result = (
            plan,
            phase,
            primary,
            retained,
            result,
        )
        super().__init__(
            "SFT unconfirmed; retain original run/checkpoint, no automatic training retry"
        )


def train_sft(plan: TrainingPlan, deps: TrainingDeps) -> TrainingReceipt:
    plan = TrainingPlan.model_validate(plan)
    retained: list[EvidenceRef] = []
    result = None
    phase = "original_dataset"
    try:
        control = deps.dataset.controls.bind(plan.dataset.operation)
        control.checkpoint()
        data = load_dataset(plan.dataset, deps.dataset)
        require_training_dataset(plan, data)
        phase = "phase_and_runtime_admission"
        deps.authority.verify(plan, data, control)
        control.checkpoint()
        raw = plan.model_dump_json().encode()
        phase = "publish_training_plan"
        plan_ref = publish_raw(
            deps.dataset.evidence,
            raw,
            training_metadata("training-plan/1"),
            retained,
            control,
        )
        phase = "original_trainer"
        result = TrainingRunResult.model_validate(
            deps.trainer.train(plan, data, control)
        )
        if (result.training_id, result.dataset_ref, result.training_release_ref) != (
            plan.training_id,
            data.receipt.dataset_ref,
            plan.training_release_ref,
        ):
            raise EvidenceIntegrityError(
                "Trainer changed exact original dataset/release/run identity"
            )
        # Only record the known original result after cancellation/expiry. This
        # fresh bounded cleanup never calls Trainer or renews a training permit.
        cleanup = plan.cleanup("result", deps.clock.utcnow())
        control = deps.dataset.controls.bind(cleanup)
        phase = "verify_original_checkpoint"
        deps.authority.verify_result(plan, data, result, control)
        control.checkpoint()
        phase = "publish_training_result"
        result_ref = publish_raw(
            deps.dataset.evidence,
            result.model_dump_json().encode(),
            training_metadata("training-run-result/1"),
            retained,
            control,
        )
        receipt = TrainingReceipt(
            plan_ref=plan_ref, result_ref=result_ref, result=result
        )
        phase = "publish_training_receipt"
        publish_raw(
            deps.dataset.evidence,
            receipt.model_dump_json().encode(),
            training_metadata("training-receipt/1"),
            retained,
            control,
        )
        return receipt
    except BaseException as error:
        raise TrainingUnconfirmed(
            plan, phase, error, tuple(retained), result
        ) from error
