"""Persistent recovery lineage. Receipt bytes remain in the evidence store.

Each new attempt retains the previous recovery writer's termination proof.
Terminal receipt references forbid subsequent attempts. Limits bound repeated
recovery, never discard history or grant automatic retries.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .evidence import EvidenceRef
from .lifecycle import AllocationToken, ResourceOwner
from .recovery import RecoveryIntent, WriterTerminationReceipt
from .validation import Contract


class RecoverySessionAttempt(Contract):
    schema_version: Literal["recovery-session-attempt/1"] = "recovery-session-attempt/1"
    intent: RecoveryIntent
    predecessor_termination: WriterTerminationReceipt | None = None
    receipt_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def bounded_private_records(self) -> Self:
        if len(self.intent.model_dump_json().encode()) > 65536:
            raise ValueError("Recovery intent exceeds 64 KiB")
        if (
            self.predecessor_termination is not None
            and len(self.predecessor_termination.model_dump_json().encode()) > 65536
        ):
            raise ValueError("Termination proof exceeds 64 KiB")
        if self.receipt_ref is not None and (
            self.receipt_ref.visibility != "private"
            or self.receipt_ref.content_schema != "recovery-receipt/1"
            or len(self.receipt_ref.model_dump_json().encode()) > 4096
        ):
            raise ValueError("Receipt reference must be private, versioned and bounded")
        return self


class RecoverySessionRecord(Contract):
    schema_version: Literal["recovery-session-record/1"] = "recovery-session-record/1"
    allocation: AllocationToken
    attempts: tuple[RecoverySessionAttempt, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def lineage(self) -> Self:
        writers: set[ResourceOwner] = set()
        operations: set[str] = set()
        for index, attempt in enumerate(self.attempts):
            intent = attempt.intent
            if intent.allocation != self.allocation:
                raise ValueError("Recovery history must retain original allocation")
            if intent.recovery_writer in writers or intent.operation_id in operations:
                raise ValueError(
                    "Recovery writer and operation identities cannot be reused"
                )
            writers.add(intent.recovery_writer)
            operations.add(intent.operation_id)
            if index == 0:
                if attempt.predecessor_termination is not None:
                    raise ValueError("First recovery has no preceding recovery writer")
            else:
                previous = self.attempts[index - 1]
                if previous.receipt_ref is not None:
                    raise ValueError("Terminal recovery cannot begin another attempt")
                if (
                    attempt.predecessor_termination is None
                    or attempt.predecessor_termination.owner
                    != previous.intent.recovery_writer
                ):
                    raise ValueError(
                        "Restart needs the exact prior recovery writer's termination"
                    )
                if intent.binding != previous.intent.binding:
                    raise ValueError(
                        "Recovery restart cannot silently replace executor versions"
                    )
        return self
