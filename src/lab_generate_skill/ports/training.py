"""Source/phase authority and one original trainer; no default grants or retries."""

from typing import Protocol
from lab_generate_skill.domain.training import TrainingPlan, TrainingRunResult
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.ports.lifecycle import OperationControl


class TrainingAuthority(Protocol):
    def verify(
        self, plan: TrainingPlan, data: LoadedDataset, control: OperationControl
    ) -> None:
        """Real phase/source/fee scope, frozen release/model, isolated writer and resume rights."""
        ...

    def verify_result(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        result: TrainingRunResult,
        control: OperationControl,
    ) -> None:
        """Read actual original checkpoint/runtime facts; status strings are not proof."""
        ...


class Trainer(Protocol):
    def train(
        self, plan: TrainingPlan, data: LoadedDataset, control: OperationControl
    ) -> TrainingRunResult:
        """Original persistent run contract/checkpoints; duplicate or unknown never starts anew.

        Runtime installation/model/resource and exclusive writer checks are mandatory.
        Explicit resume uses the same original contract and verified checkpoint, never
        an empty history. Errors preserve original and cleanup facts. No auto retry.
        """
        ...
