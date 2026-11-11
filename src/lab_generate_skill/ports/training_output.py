"""Original execution/closure authority and native complete-file snapshot reader."""

from pathlib import Path
from typing import Protocol, Literal, Any
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    SFTCheckpoint,
    NativeTrainingExecution,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from .lifecycle import OperationControl


class TrainingExecution(Protocol):
    def verify(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> None: ...
    def execute(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> EvidenceRef:
        """Original registered supervised worker only; no inline fallback/new ledger."""
        ...

    def close(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> ClosureReceipt:
        """Actual original worker/GPU resource tree closure, not only ProcessTermination."""
        ...

    def abort(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        primary: BaseException,
        control: OperationControl,
    ) -> None: ...


class TrainingOutputAuthority(Protocol):
    def verify(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        closure: ClosureReceipt,
        execution_ref: EvidenceRef,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> NativeTrainingExecution:
        """Actual installed original producer, writer/output and full closure proofs.

        Snapshot equality/metadata never grants permission. Reader rights remain
        explicit, no model launch/write permission or frozen-Map scope reuse.
        """
        ...


class TrainingWorkerAuthority(Protocol):
    def verify_capture(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        token: AllocationToken,
        worker: ProcessIdentity,
        installation_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        """Actual once-returned installed producer and original read scope, before filesystem I/O."""
        ...

    def verify_return(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        control: OperationControl,
    ) -> None:
        """Actual installed original worker in original return stage, before publication."""
        ...

    def verify_closed(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        closure: ClosureReceipt,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> None:
        """Independent original protocol/source/worker/resource proof, real full closure/read rights."""
        ...


class TrainingCheckpoints(Protocol):
    def publish(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        closure: ClosureReceipt,
        execution_ref: EvidenceRef,
        control: OperationControl,
    ) -> EvidenceRef: ...
    def read(
        self, reference: EvidenceRef, data: LoadedDataset, control: OperationControl
    ) -> SFTCheckpoint: ...
