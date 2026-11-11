"""Bounded worker CAS declarations under the original acquired Map capability."""

from pathlib import Path
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from .site_access import OriginalMapSiteAccess


class OriginalMapSelectionReader:
    def __init__(self, access: OriginalMapSiteAccess) -> None:
        if access.participant != "worker":
            raise ValueError("Fixed original Map worker required")
        self.access = access

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        reference = EvidenceRef.model_validate(reference)
        if (
            reference.visibility != "private"
            or not 0 < reference.size_bytes <= 64 * 1024**2
        ):
            raise EvidenceIntegrityError(
                "Bounded original private CAS declaration required"
            )
        self.access.observe(control)
        store = FileEvidenceStore(
            Path(self.access.inputs.evidence_root), initialize=False
        )
        raw = store.read(reference)
        self.access.observe(control)
        return raw
