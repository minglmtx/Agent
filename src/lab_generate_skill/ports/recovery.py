"""Recovery-only ports. No acquire, initialize, Actor or provider-close fallback.

The session serializes recovery across workers and persists intent before
effects. A crashed prior recovery writer AND its children must be proven ended
before another session may begin. Lease age or lock-file existence is not proof.
Backend restore is idempotent for the same original allocation/plan, permitting
reconciliation after partial recovery; never recreate the resource.
"""

from contextlib import AbstractContextManager
from typing import Protocol

from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
)
from lab_generate_skill.domain.recovery import (
    RecoveryBinding,
    RecoveryIntent,
    RecoveryObservation,
    RecoveryReceipt,
    RecoveryResult,
    WriterTerminationReceipt,
)


class TerminationVerifier(Protocol):
    """Validate actual trusted authority facts, original incarnation and children.

    Raise when live/unknown/mismatched; parsing a typed receipt is insufficient.
    """

    def verify(
        self,
        allocation: AllocationToken,
        receipt: WriterTerminationReceipt,
        op: OperationContext,
    ) -> None: ...


class RecoverySession(Protocol):
    def checkpoint(self) -> None: ...
    def read(self) -> RecoveryReceipt | None: ...
    def begin(self, intent: RecoveryIntent) -> None: ...
    def commit(self, receipt: RecoveryReceipt) -> None: ...


class WriterQuiescence(Protocol):
    """Obtain trusted end-of-writer AND descendant proof; live/unknown raises.

    Used for a prior recovery writer, independently of the original task writer.
    Must bind the exact recorded incarnation; a released file lock is not proof.
    """

    def confirm_ended(
        self, writer: ResourceOwner, op: OperationContext
    ) -> WriterTerminationReceipt: ...


class RecoverySessions(Protocol):
    def hold(
        self, allocation: AllocationToken, writer: ResourceOwner, op: OperationContext
    ) -> AbstractContextManager[RecoverySession]: ...


class RecoveryBackend(Protocol):
    @property
    def binding(self) -> RecoveryBinding: ...
    def inspect(
        self, allocation: AllocationToken, op: OperationContext
    ) -> RecoveryObservation: ...
    def restore(
        self,
        allocation: AllocationToken,
        recovery: RecoveryPlan,
        control: RecoverySession,
        op: OperationContext,
    ) -> RecoveryResult: ...


class RecoveryExecutor(Protocol):
    def restore(
        self,
        allocation: AllocationToken,
        recovery: RecoveryPlan,
        termination: WriterTerminationReceipt,
        op: OperationContext,
    ) -> RecoveryReceipt: ...
