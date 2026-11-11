"""One guarded original training invocation, not a launcher or phase authority."""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.validation import Sha256
from .lifecycle import OperationControl


class TrainingWorkerBackend(Protocol):
    def execute(
        self, contract_sha256: Sha256, control: OperationControl
    ) -> EvidenceRef:
        """Original prequalified dataset/core only; never retry or manufacture admission."""
        ...

    def close(self, control: OperationControl) -> None:
        """Child-local cleanup only; full original GPU/resource closure remains external."""
        ...
