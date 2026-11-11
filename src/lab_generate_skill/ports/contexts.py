"""Private qualification transport, distinct from public Generator inputs.

Authority is mandatory on production and consumption. In addition to historical
StateAuthority checks, it verifies complete preregistered source resources,
source permission for this caller/attempt, projection provenance and actual
equivalence evidence. Cross-attempt source reads are explicit here, not a relaxed
StateRecords permission. Implementations never rerun environment actions.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.ports.state_records import StateAuthority
from lab_generate_skill.ports.lifecycle import OperationControl


class ContextInputRead(Protocol):
    """One call's verified bodies; each gate still checks current authority."""

    @property
    def inputs(self) -> PublicContextInputs: ...
    def verify_baseline(
        self, inputs: object, receipt: object, op: OperationContext
    ) -> None: ...
    def verify_reset(
        self, inputs: object, receipt: object, op: OperationContext
    ) -> None: ...
    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class ContextInputReads(Protocol):
    def read_inputs(
        self,
        receipt: PublicContextReceipt,
        operation: OperationContext,
        control: OperationControl,
    ) -> ContextInputRead | None: ...


@runtime_checkable
class ContextCurrentChecks(Protocol):
    def check_context_current(
        self, op: OperationContext, control: OperationControl
    ) -> None: ...


@runtime_checkable
class ContextFactReads(ContextCurrentChecks, Protocol):
    """Existing controlled whole-graph proof plus fresh original storage gates."""

    def load_context_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> tuple[PublicContextReceipt, PublicContextInputs]: ...


class ContextAuthority(StateAuthority, Protocol):
    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None: ...
    def verify_equivalence(
        self,
        inputs: EquivalenceInputs,
        receipt: EquivalenceReceipt,
        op: OperationContext,
    ) -> None: ...


class ContextRecords(Protocol):
    def publish_context(
        self, receipt: PublicContextReceipt, op: OperationContext
    ) -> EvidenceRef: ...
    def load_context(
        self, reference: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt: ...
    def publish_equivalence(
        self, receipt: EquivalenceReceipt, op: OperationContext
    ) -> EvidenceRef: ...
    def load_equivalence(
        self, reference: EvidenceRef, op: OperationContext
    ) -> EquivalenceReceipt: ...
