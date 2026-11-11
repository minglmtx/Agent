"""Immutable state summaries, with mandatory historical semantic verification.

Authority verifies real provider/claim/allocation, complete check policy,
measured-state truth and physical ordering/closure. It must not rerun preparation
or cleanup. Unit authorities cannot be installed as a production default.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.reset_publication import PublishedReset
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext


class StateAuthority(Protocol):
    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None: ...
    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None: ...


@runtime_checkable
class ResetInputAuthority(Protocol):
    def verify_reset_inputs(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        """Same invocation's completed native check bodies; fresh current authority.

        An independent/default reset verification still recomputes native facts.
        No checkpoint, receipt or copied input may create this producer state.
        """
        ...


@runtime_checkable
class BaselineInputReads(Protocol):
    def load_baseline_inputs(
        self, request: BaselineReadRequest, control: OperationControl
    ) -> BaselineReadBodies | None: ...


class StateRecords(Protocol):
    def publish_baseline(
        self, receipt: BaselineReceipt, op: OperationContext
    ) -> EvidenceRef: ...
    def load_baseline(
        self, reference: EvidenceRef, op: OperationContext
    ) -> BaselineReceipt: ...
    def publish_reset(
        self, receipt: ResetReceipt, op: OperationContext
    ) -> EvidenceRef: ...
    def load_reset(
        self, reference: EvidenceRef, op: OperationContext
    ) -> ResetReceipt: ...


@runtime_checkable
class VerifiedResetPublication(Protocol):
    """Same-call graph verification, exact readback and fresh consumption gate."""

    def publish_reset_verified(
        self, receipt: ResetReceipt, op: OperationContext
    ) -> EvidenceRef: ...


@runtime_checkable
class ResetInputPublication(Protocol):
    """Direct Reset producer bodies; complete references and current authority remain."""

    def publish_reset_inputs(
        self, receipt: ResetReceipt, inputs: ResetInputs, op: OperationContext
    ) -> PublishedReset: ...

    def load_reset_publication(
        self, publication: PublishedReset, op: OperationContext
    ) -> ResetReceipt: ...
