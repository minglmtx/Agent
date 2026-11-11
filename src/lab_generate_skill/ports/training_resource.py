"""Mandatory original trainer ownership and read rights, no default grants."""

from typing import Literal, Protocol
from lab_generate_skill.domain.training_resource import (
    TrainingResourceSpec,
    TrainingLaunch,
    TrainingResourceAcquired,
    TrainingStepCleanup,
    TrainingStepClosed,
)
from lab_generate_skill.domain.training_output import NativeTrainingExecution
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from .lifecycle import OperationControl


class TrainingResourceAuthority(Protocol):
    def authorize_start(
        self, spec: TrainingResourceSpec, control: OperationControl
    ) -> None:
        """Real original job/isolated writer/fixed install/model/GPU and explicit resume rights; no training permit."""
        ...

    def authorize_training(
        self, launch: TrainingLaunch, data: LoadedDataset, control: OperationControl
    ) -> None:
        """Actual original source/phase/fees and known-request state immediately before train. No label grant."""
        ...

    def verify_started(
        self,
        spec: TrainingResourceSpec,
        acquired: TrainingResourceAcquired,
        control: OperationControl,
    ) -> None: ...

    def verify_closed(
        self,
        spec: TrainingResourceSpec,
        handle: TrainingStepCleanup,
        termination: ProcessTermination,
        observed: TrainingStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Verify the caller's single actual full-tree observation; do not requery a removed cgroup."""
        ...

    def authorize_read(
        self,
        spec: TrainingResourceSpec,
        native: NativeTrainingExecution,
        closure: ClosureReceipt,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> None:
        """Actual closed-source/namespace permission, never resource/model dispatch permission."""
        ...
