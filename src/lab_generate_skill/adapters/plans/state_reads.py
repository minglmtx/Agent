"""Bounded reads of declared state contracts, never arbitrary JSON traversal."""

from typing import TypeVar
from lab_generate_skill.domain.evidence import EvidenceRef, Visibility
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


class StateReads:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        raw = self.store.read(reference, control=control)
        control.checkpoint()
        return raw

    def parse(
        self,
        reference: EvidenceRef,
        schema: str,
        model: type[T],
        control: OperationControl,
        *,
        visibility: Visibility = "private",
        expected_reference: EvidenceRef | None = None,
    ) -> T:
        reference = EvidenceRef.model_validate(reference)
        # The frozen-output caller supplies the complete reference from its
        # selected immutable manifest. CAS bytes alone do not bind producer,
        # schema or visibility. This is content identity, never live authority.
        if expected_reference is not None:
            expected_reference = EvidenceRef.model_validate(expected_reference)
            if reference != expected_reference:
                raise OwnershipConflict("Frozen input changed its complete reference")
        if (reference.content_schema, reference.visibility) != (schema, visibility):
            raise ValueError("Expected " + visibility + " " + schema)
        result = model.model_validate_json(self.read(reference, control))
        control.checkpoint()
        return result

    def dependencies(
        self, values: tuple[Contract, ...], control: OperationControl
    ) -> None:
        for reference in dict.fromkeys(evidence_references(values)):
            self.read(reference, control)
