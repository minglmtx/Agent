"""Frozen construction storage bounds and operation lineage; no I/O.

Reserve full bounded event bytes for each remaining result/method step. This
does not guarantee disk availability or fit arbitrarily large provider output.
Large verified facts that cannot commit are retained separately for diagnosis.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .construction_state import ConstructionProgress
from .errors import JournalCapacityExceeded
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .validation import Contract


class ConstructionCapacity(Contract):
    schema_version: Literal["construction-capacity/1"] = "construction-capacity/1"
    max_events: int = Field(ge=91, le=256)
    max_bytes: int = Field(ge=1, le=8 * 1024 * 1024)
    max_event_bytes: int = Field(ge=1, le=8 * 1024 * 1024)

    @model_validator(mode="after")
    def normal_method_fits(self) -> Self:
        if 91 * (self.max_event_bytes + 1) > self.max_bytes:
            raise ValueError("Normal construction completion cannot fit byte budget")
        return self


class ConstructionSnapshot(Contract):
    schema_version: Literal["construction-snapshot/1"] = "construction-snapshot/1"
    capacity: ConstructionCapacity
    creation_operation: OperationContext
    progress: ConstructionProgress

    @model_validator(mode="after")
    def consistent_and_bounded(self) -> Self:
        op = self.creation_operation
        owner = self.progress.plan.run.owner
        if (
            (op.run_id, op.owner_id) != (owner.run_id, owner.owner_id)
            or op.attempt_id is not None
            or op.mode != "execute"
        ):
            raise ValueError(
                "Creation requires its original run-level execute operation"
            )
        if any(
            event.operation.operation_id == op.operation_id
            for event in self.progress.events
        ):
            raise ValueError("Creation operation cannot become a progress event")
        usage = self.progress.capacity_usage()
        shell = (
            len(self.model_dump_json().encode())
            - sum(size for size, _ in usage)
            - max(0, len(usage) - 1)
        )
        initial = ConstructionProgress(plan=self.progress.plan).remaining_event_slots()
        if (
            initial > self.capacity.max_events
            or shell + initial * (self.capacity.max_event_bytes + 1)
            > self.capacity.max_bytes
        ):
            raise JournalCapacityExceeded(
                "Frozen construction envelope leaves no completion space"
            )
        used = shell
        for count, (size, reserve) in enumerate(usage, start=1):
            used += size + int(count > 1)
            if size > self.capacity.max_event_bytes:
                raise JournalCapacityExceeded(
                    "Construction event exceeds frozen byte ceiling"
                )
            if (
                count + reserve > self.capacity.max_events
                or used + reserve * (self.capacity.max_event_bytes + 1)
                > self.capacity.max_bytes
            ):
                raise JournalCapacityExceeded(
                    "Construction commit would consume completion reserve"
                )
        return self


class ConstructionCommitUnconfirmed(RuntimeError):
    """Verified fact is in CAS, but its history commit/cleanup was not confirmed.

    Inspect/replay this exact event; do not repeat model calls or attempts. The
    snapshot may already contain the event. Original exceptions remain cause.
    """

    reason_code = "CONSTRUCTION_COMMIT_UNCONFIRMED"

    def __init__(self, event_ref: EvidenceRef) -> None:
        self.event_ref = event_ref
        super().__init__("Saved construction fact requires commit reconciliation")
