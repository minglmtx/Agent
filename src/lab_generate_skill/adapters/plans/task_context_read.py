"""One synchronous source graph, original current caller gates, final full proof.

No permission is stored with the immutable body. The object cannot escape its
original thread, operation or three-check sequence, and is cleared on exit.
"""

import os
from collections.abc import Callable
import threading
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.ports.contexts import ContextFactReads
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalSourceContextRead:
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        sources: ContextFactReads,
        reference: EvidenceRef,
        receipt: PublicContextReceipt,
        inputs: PublicContextInputs,
        operation: OperationContext,
        control: OperationControl,
        *,
        recheck: (
            Callable[
                [OperationContext, OperationControl],
                tuple[PublicContextReceipt, PublicContextInputs],
            ]
            | None
        ) = None,
    ) -> None:
        self.owner, self.sources, self.reference = owner, sources, reference
        self.receipt, self.operation, self.control = receipt, operation, control
        self._inputs: PublicContextInputs | None = inputs
        self._thread = os.getpid(), threading.get_ident()
        self._phase = 0
        self.recheck = recheck

    def _owned(self) -> None:
        if self._thread != (os.getpid(), threading.get_ident()) or self._inputs is None:
            raise OwnershipConflict("Source context read left original call/thread")

    @property
    def inputs(self) -> PublicContextInputs:
        self._owned()
        assert self._inputs is not None
        return self._inputs

    def _gate(self, phase: int, op: OperationContext) -> PublicContextInputs:
        self._owned()
        if op != self.operation or phase != self._phase:
            raise OwnershipConflict(
                "Source context checks changed original operation/order"
            )
        self.control.checkpoint()
        self.owner.caller(op, self.control)
        self.sources.check_context_current(op, self.control)
        self._phase += 1
        return self.inputs

    def verify_baseline(
        self, inputs: object, receipt: object, op: OperationContext
    ) -> None:
        source = self._gate(0, op)
        if (inputs, receipt) != (source.baseline_inputs, source.baseline):
            raise OwnershipConflict(
                "Source baseline differs from complete original proof"
            )

    def verify_reset(
        self, inputs: object, receipt: object, op: OperationContext
    ) -> None:
        source = self._gate(1, op)
        if (inputs, receipt) != (source.reset_inputs, source.reset):
            raise OwnershipConflict("Source Reset differs from complete original proof")

    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None:
        source = self._gate(2, op)
        if inputs != source or receipt != self.receipt:
            raise OwnershipConflict("Source context changed original immutable graph")
        # Preserve a complete returning proof, not an old dynamic ready flag.
        actual, final = (
            self.sources.load_context_inputs(self.reference, op)
            if self.recheck is None
            else self.recheck(op, self.control)
        )
        if actual != receipt or final != source:
            raise OwnershipConflict("Original source graph changed before return")
        self.owner.caller(op, self.control)
        self.control.checkpoint()

    def close(self) -> None:
        self._owned()
        self._inputs = None
        self.recheck = None
