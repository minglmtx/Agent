"""Canonical private evidence reads shared by this site's qualification checks."""

from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


class ShoppingStateReads:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def read(
        self, ref: EvidenceRef, schema: str, model: type[T], control: OperationControl
    ) -> T:
        private_state_ref(ref, schema)
        if ref.media_type != "application/json":
            raise ValueError("Shopping state evidence must be private JSON")
        raw = self.store.read(ref, control=control)
        value = model.model_validate_json(raw)
        if value.model_dump_json().encode() != raw:
            raise ValueError("Noncanonical original Shopping state evidence")
        control.checkpoint()
        return value

    @staticmethod
    def checks(
        names: tuple[str, ...], refs: tuple[EvidenceRef, ...], reason: str
    ) -> StateChecks:
        return StateChecks(
            required=names,
            checks=tuple(
                CheckResult(name=name, status="pass", reason_code=reason, evidence=refs)
                for name in names
            ),
        )
