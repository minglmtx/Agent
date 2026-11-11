"""Optional same-call complete-body and canonical-document input handoff."""

from typing import Protocol, TypeVar, runtime_checkable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from .lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


@runtime_checkable
class VerifiedEvidenceInputs(Protocol):
    def read_verified(
        self, reference: EvidenceRef, control: OperationControl
    ) -> VerifiedEvidenceBody: ...

    def read_document(
        self,
        reference: EvidenceRef,
        model: type[T],
        limit: int,
        control: OperationControl,
        *,
        canonical: bool,
    ) -> T: ...
