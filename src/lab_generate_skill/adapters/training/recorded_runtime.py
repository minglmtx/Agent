"""Original supervised execution -> actual close -> complete checkpoint evidence."""

from pathlib import Path
from typing import Any
from lab_generate_skill.domain.training import TrainingPlan, TrainingRunResult
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    require_training_closure,
)
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.training_output import (
    TrainingExecution,
    TrainingCheckpoints,
)
from .inputs import build_sft_inputs


class RecordedTrainingRuntime:
    def __init__(
        self,
        workspace: Path,
        publication_root: Path,
        max_files: int,
        max_file_bytes: int,
        max_total_bytes: int,
        execution: TrainingExecution,
        checkpoints: TrainingCheckpoints,
    ) -> None:
        if (
            not isinstance(workspace, Path)
            or not workspace.is_absolute()
            or not isinstance(publication_root, Path)
            or not publication_root.is_absolute()
            or publication_root == workspace
            or not publication_root.is_relative_to(workspace)
        ):
            raise ValueError("Trusted distinct workspace publication root required")
        if (
            any(
                type(n) is not int or not 1 <= n <= 2 * 1024**4
                for n in (max_files, max_file_bytes, max_total_bytes)
            )
            or max_files > 100000
            or max_file_bytes > max_total_bytes
        ):
            raise ValueError("Explicit complete native file/storage budgets required")
        if any(
            not callable(getattr(obj, name, None))
            for obj, name in (
                (execution, "verify"),
                (execution, "execute"),
                (execution, "close"),
                (execution, "abort"),
                (checkpoints, "publish"),
                (checkpoints, "read"),
            )
        ):
            raise ValueError(
                "Original supervised execution and complete-file evidence ports required"
            )
        self.workspace, self.publication_root = workspace, publication_root
        self.limits = (max_files, max_file_bytes, max_total_bytes)
        self.execution, self.checkpoints = execution, checkpoints
        self.bound: TrainingOutputPlan | None = None
        self.state = "new"
        self.execution_ref: EvidenceRef | None = None
        self.checkpoint_ref: EvidenceRef | None = None
        self.last_closure: ClosureReceipt | None = None

    def _bound(self, plan: TrainingPlan, output: Path) -> TrainingOutputPlan:
        if (
            self.bound is None
            or self.bound.training != plan
            or self.bound.output_root != str(output)
        ):
            raise EvidenceIntegrityError(
                "Runtime changed original training plan/output"
            )
        return self.bound

    def verify(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> None:
        if self.state != "new":
            raise InvalidTransition(
                "Original runtime admission is once-only; unknown/duplicate cannot relaunch"
            )
        self.bound = TrainingOutputPlan(
            training=plan,
            workspace_root=str(self.workspace),
            output_root=str(output),
            publication_root=str(self.publication_root),
            max_files=self.limits[0],
            max_file_bytes=self.limits[1],
            max_total_bytes=self.limits[2],
        )
        self.state = "admitting"
        self.execution.verify(plan, data, output, control)
        control.checkpoint()
        self.state = "admitted"

    def execute(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> None:
        self._bound(plan, output)
        if (
            self.state != "admitted"
            or build_sft_inputs(plan, data, output).contract != contract
        ):
            raise InvalidTransition(
                "Only the original admitted exact native request can execute once"
            )
        self.state = "executing"
        returned = EvidenceRef.model_validate(
            self.execution.execute(plan, data, output, contract, control)
        )
        private_state_ref(returned, "sft-native-execution/1")
        self.execution_ref = returned
        self.state = "returned"

    def finish(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> TrainingRunResult:
        bound = self._bound(plan, output)
        if (
            self.state != "returned"
            or self.execution_ref is None
            or build_sft_inputs(plan, data, output).contract != contract
        ):
            raise InvalidTransition(
                "Unknown/unreturned native request cannot publish a training result"
            )
        self.state = "closing"
        closure = ClosureReceipt.model_validate(
            self.execution.close(plan, data, output, control)
        )
        self.last_closure = closure
        require_training_closure(bound, closure)
        self.state = "closed"
        self.checkpoint_ref = self.checkpoints.publish(
            bound, data, closure, self.execution_ref, control
        )
        snapshot = self.checkpoints.read(self.checkpoint_ref, data, control)
        if (
            snapshot.plan != bound
            or snapshot.execution_ref != self.execution_ref
            or snapshot.closure != closure
        ):
            raise EvidenceIntegrityError(
                "Checkpoint changed original worker/output/closure"
            )
        assert data.receipt.dataset_ref is not None
        n = snapshot.native
        result = TrainingRunResult(
            training_id=plan.training_id,
            dataset_ref=data.receipt.dataset_ref,
            training_release_ref=plan.training_release_ref,
            contract_sha256=n.contract_sha256,
            status=n.status,
            optimizer_steps=n.optimizer_steps,
            planned_optimizer_steps=n.planned_optimizer_steps,
            checkpoint_ref=self.checkpoint_ref,
            runtime_evidence_refs=tuple(
                dict.fromkeys((self.execution_ref, *closure.evidence))
            ),
        )
        self.state = "published"
        return result

    def abort(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        primary: BaseException,
        control: OperationControl,
    ) -> None:
        self._bound(plan, output)
        self.state = "aborting"
        self.execution.abort(plan, data, output, primary, control)
        self.state = "aborted"
