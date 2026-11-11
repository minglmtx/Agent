"""Synchronous test-only evidence; no claim of supervised filesystem deadlines.

Optional control is only for fixture setup/readback. Production ports require
control and never import this adapter. Worker primitive tests keep the primitive.
"""

from lab_generate_skill.adapters.storage.filesystem import (
    FileEvidenceStore as PrimitiveStore,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl


class EvidenceFixtureStore(PrimitiveStore):
    __test__ = False

    def read(
        self, reference: EvidenceRef, control: OperationControl | None = None
    ) -> bytes:
        if control is not None:
            control.checkpoint()
        result = super().read(reference)
        if control is not None:
            control.checkpoint()
        return result

    def put(
        self,
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if control is not None:
            control.checkpoint()
        result = super().put(data, metadata, exchange_id=exchange_id)
        if control is not None:
            control.checkpoint()
        return result
