"""Complete-byte CAS IO for original preparation, with partial refs retained."""

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)
from .task_preparation_state import TaskPreparationState


class TaskPreparationEvidence:
    def __init__(self, store: EvidenceStore, state: TaskPreparationState) -> None:
        self.store, self.state = store, state

    def read(
        self, ref: EvidenceRef, control: OperationControl, limit: int = 2 * 1024**2
    ) -> bytes:
        require_complete_read_bound(ref, limit)
        control.checkpoint()
        raw = self.store.read(ref, control=control)
        require_complete_bytes(ref, raw)
        control.checkpoint()
        return raw

    def put_raw(
        self, raw: bytes, schema: str, control: OperationControl
    ) -> EvidenceRef:
        control.checkpoint()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="task-preparation-v1",
        )
        candidate = evidence_reference(raw, metadata)
        try:
            ref = EvidenceRef.model_validate(
                self.store.put(raw, metadata, control=control)
            )
        except BaseException as error:
            setattr(error, "preparation_candidate_reference", candidate)
            raise
        self.state.references.append(ref)
        require_complete_bytes(ref, raw)
        if (ref.media_type, ref.content_schema, ref.visibility, ref.producer) != (
            metadata.media_type,
            metadata.content_schema,
            metadata.visibility,
            metadata.producer,
        ):
            raise EvidenceIntegrityError("Preparation store changed original metadata")
        control.checkpoint()
        return ref

    def put(self, value: Contract, control: OperationControl) -> EvidenceRef:
        return self.put_raw(
            value.model_dump_json().encode(),
            value.model_dump()["schema_version"],
            control,
        )
