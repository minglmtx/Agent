"""Unified qualified dataset to the one original LoRA algorithm and checkpoints."""

import hashlib
import json
from pathlib import Path
from lab_generate_skill.domain.training import TrainingPlan, TrainingRunResult
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    Clock,
)
from lab_generate_skill.ports.training_runtime import TrainingRuntime
from lab_generate_skill.policies.training_admission import require_training_dataset
from .inputs import build_sft_inputs


class TrainingBackendUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: TrainingPlan,
        output: Path,
        phase: str,
        primary: BaseException,
        cleanup_errors: tuple[BaseException, ...],
    ) -> None:
        self.plan, self.output, self.phase, self.primary = plan, output, phase, primary
        self.cleanup_errors = cleanup_errors
        super().__init__(
            "Original SFT backend unconfirmed; preserve manifest/checkpoints, no automatic retry"
        )


class OriginalSFTTrainer:
    def __init__(
        self,
        output_root: Path,
        runtime: TrainingRuntime,
        controls: OperationControls,
        clock: Clock,
    ) -> None:
        if (
            not isinstance(output_root, Path)
            or not output_root.is_absolute()
            or ".." in output_root.parts
        ):
            raise ValueError("Explicit canonical training output root required")
        if any(
            not callable(getattr(obj, name, None))
            for obj, name in (
                (runtime, "verify"),
                (runtime, "execute"),
                (runtime, "finish"),
                (runtime, "abort"),
                (controls, "bind"),
                (clock, "utcnow"),
            )
        ):
            raise ValueError(
                "Actual original runtime/writer/model/checkpoint authority required"
            )
        self.output_root, self.runtime, self.controls, self.clock = (
            output_root,
            runtime,
            controls,
            clock,
        )

    def train(
        self, plan: TrainingPlan, data: LoadedDataset, control: OperationControl
    ) -> TrainingRunResult:
        plan = TrainingPlan.model_validate(plan)
        require_training_dataset(plan, data)
        output = self.output_root / (
            "sft-" + hashlib.sha256(plan.training_id.encode()).hexdigest()
        )
        phase = "runtime_admission"
        try:
            control.checkpoint()
            self.runtime.verify(plan, data, output, control)
            request = build_sft_inputs(plan, data, output)
            contract = request.contract
            phase = "original_training_algorithm"
            self.runtime.execute(plan, data, output, contract, control)
            phase = "original_checkpoint_and_runtime_facts"
            cleanup = plan.cleanup("backend-result", self.clock.utcnow())
            result = TrainingRunResult.model_validate(
                self.runtime.finish(
                    plan, data, output, contract, self.controls.bind(cleanup)
                )
            )
            digest = hashlib.sha256(
                json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            if (
                result.training_id,
                result.dataset_ref,
                result.training_release_ref,
                result.contract_sha256,
            ) != (
                plan.training_id,
                data.receipt.dataset_ref,
                plan.training_release_ref,
                digest,
            ):
                raise EvidenceIntegrityError(
                    "Training runtime changed original run/dataset/contract/release"
                )
            return result
        except BaseException as error:
            cleanup_errors = []
            try:
                cleanup = plan.cleanup("backend-abort", self.clock.utcnow())
                self.runtime.abort(
                    plan, data, output, error, self.controls.bind(cleanup)
                )
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
            raise TrainingBackendUnconfirmed(
                plan, output, phase, error, tuple(cleanup_errors)
            ) from error
