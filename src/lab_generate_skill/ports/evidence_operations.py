"""Physical operation binding injected into storage; never business permission."""

from typing import Protocol
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


class PreparedStorageOperation(Protocol):
    @property
    def operation(self) -> OperationContext: ...

    @property
    def control(self) -> OperationControl: ...


class EvidenceOperationFactory(Protocol):
    @property
    def binding(self) -> EvidenceSessionBinding: ...

    def prepare(
        self, exchange_id: str, control: OperationControl
    ) -> PreparedStorageOperation: ...
