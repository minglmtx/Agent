"""I/O-free operation, ownership and cleanup contracts.

Inputs are explicit identities, aware deadlines and recovery evidence. Outputs
are immutable tokens/receipts; constructing a token is NOT durable registration
and constructing a receipt is NOT proof that a resource has been cleaned.
ResourceJournal and independent review establish those facts respectively.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .errors import InvalidTransition
from .evidence import EvidenceRef
from .validation import Contract, Identifier, NonEmptyText


class CancellationRef(Contract):
    """Live control channel identity, not an immutable evidence-object digest.

    Cancellation facts are persisted separately by the control adapter. Keeping
    the reference stable must not freeze the channel's value at operation start.
    """

    schema_version: Literal["cancellation-ref/1"] = "cancellation-ref/1"
    channel_id: Identifier
    run_id: Identifier
    owner_id: Identifier


class OperationContext(Contract):
    """Bounded operation metadata; never carries services, secrets or handles."""

    schema_version: Literal["operation-context/1"] = "operation-context/1"
    operation_id: Identifier
    run_id: Identifier
    owner_id: Identifier
    attempt_id: Identifier | None = None
    allocation_id: Identifier | None = None
    recovery_ref: EvidenceRef | None = None
    cancellation_ref: CancellationRef | None = None
    deadline: AwareDatetime
    mode: Literal["execute", "cleanup"] = "execute"
    parent_operation_id: Identifier | None = None

    @field_validator("deadline")
    @classmethod
    def utc_deadline(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def distinct_cleanup_identity(self) -> Self:
        if self.mode == "cleanup" and self.parent_operation_id is None:
            raise ValueError("Cleanup requires the original operation identity")
        if self.parent_operation_id == self.operation_id:
            raise ValueError("An operation cannot be its own parent")
        if self.cancellation_ref is not None and (
            self.cancellation_ref.run_id != self.run_id
            or self.cancellation_ref.owner_id != self.owner_id
        ):
            raise ValueError("Cancellation channel must belong to this run and owner")
        return self

    def cleanup(
        self, operation_id: str, *, now: datetime, seconds: float
    ) -> "OperationContext":
        """Create an independent bounded cleanup period after an expired action.

        Parent cancellation is not inherited. Explicit cancellation of cleanup
        can be supplied by its own controller; no execution privilege is gained.
        Invalid numeric budgets raise ValueError; nonnumeric types raise TypeError.
        The new deadline must fit datetime without changing the original context.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Cleanup clock must be timezone-aware")
        if not isinstance(seconds, (int, float)):
            raise TypeError("Cleanup duration must be an int or float")
        try:
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Cleanup duration must be positive and finite")
            deadline = now + timedelta(seconds=seconds)
        except OverflowError as error:
            raise ValueError(
                "Cleanup deadline is outside the supported range"
            ) from error
        return OperationContext(
            operation_id=operation_id,
            run_id=self.run_id,
            owner_id=self.owner_id,
            attempt_id=self.attempt_id,
            allocation_id=self.allocation_id,
            recovery_ref=self.recovery_ref,
            deadline=deadline,
            mode="cleanup",
            parent_operation_id=self.operation_id,
        )


class ResourceOwner(Contract):
    """Original writer identity; a lease expiry never changes this owner."""

    schema_version: Literal["resource-owner/1"] = "resource-owner/1"
    run_id: Identifier
    owner_id: Identifier
    job_id: Identifier
    worker_id: Identifier


class RecoveryPlan(Contract):
    """Predeclared recovery target and coverage, persisted before task writes."""

    schema_version: Literal["recovery-plan/1"] = "recovery-plan/1"
    recovery_id: Identifier
    owner: ResourceOwner
    attempt_id: Identifier | None = None
    baseline_ref: EvidenceRef
    restore_component_id: Identifier
    restore_component_version: NonEmptyText
    state_coverage: tuple[NonEmptyText, ...] = Field(min_length=1)
    protected_state: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def explicit_private_coverage(self) -> Self:
        if self.baseline_ref.visibility != "private":
            raise ValueError("Recovery baseline must stay in the trusted view")
        if len(set(self.state_coverage)) != len(self.state_coverage):
            raise ValueError("Recovery coverage entries must be unique")
        if any(ref.visibility != "private" for ref in self.protected_state):
            raise ValueError("Protected-state evidence must stay private")
        return self


class AllocationToken(Contract):
    """Resource intent registered before acquire, including its recovery plan."""

    schema_version: Literal["allocation-token/1"] = "allocation-token/1"
    allocation_id: Identifier
    owner: ResourceOwner
    scope: Literal["batch", "attempt"]
    attempt_id: Identifier | None = None
    resource_kind: Identifier
    expected_resource_id: Identifier
    provider_id: Identifier
    provider_version: NonEmptyText
    recovery_ref: EvidenceRef

    @model_validator(mode="after")
    def scope_and_recovery(self) -> Self:
        if (self.scope == "attempt") != (self.attempt_id is not None):
            raise ValueError("Attempt scope alone requires an attempt identity")
        if (
            self.recovery_ref.visibility != "private"
            or self.recovery_ref.content_schema != "recovery-plan/1"
        ):
            raise ValueError("Allocation must reference a private recovery-plan/1")
        return self


ResourceState = Literal[
    "registered", "acquiring", "acquired", "closing", "closed", "quarantined"
]


def require_resource_transition(before: ResourceState, after: ResourceState) -> None:
    """Reject reopening/reusing a closed or quarantined allocation identity."""
    allowed: dict[ResourceState, frozenset[ResourceState]] = {
        "registered": frozenset(("acquiring", "closing", "quarantined")),
        "acquiring": frozenset(("acquired", "closing", "quarantined")),
        "acquired": frozenset(("closing", "quarantined")),
        "closing": frozenset(("closed", "quarantined")),
        "closed": frozenset(),
        "quarantined": frozenset(),
    }
    if after not in allowed[before]:
        raise InvalidTransition(f"Resource cannot transition from {before} to {after}")


class ResourceEvent(Contract):
    """Durable operation outcome; evidence is mandatory after registration."""

    schema_version: Literal["resource-event/2"] = "resource-event/2"
    operation: OperationContext
    state: ResourceState
    evidence: tuple[EvidenceRef, ...] = ()

    @property
    def operation_id(self) -> str:
        return self.operation.operation_id


class ResourceRecord(Contract):
    """Append-only logical history represented by one atomic snapshot."""

    schema_version: Literal["resource-record/2"] = "resource-record/2"
    token: AllocationToken
    events: tuple[ResourceEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_history(self) -> Self:
        if self.events[0].state != "registered":
            raise ValueError("Resource history must start with durable registration")
        if len({event.operation_id for event in self.events}) != len(self.events):
            raise ValueError("A resource operation may commit only once")
        for event in self.events:
            op = event.operation
            if (
                op.run_id,
                op.owner_id,
                op.attempt_id,
                op.allocation_id,
                op.recovery_ref,
            ) != (
                self.token.owner.run_id,
                self.token.owner.owner_id,
                self.token.attempt_id,
                self.token.allocation_id,
                self.token.recovery_ref,
            ):
                raise ValueError("Resource event must retain exact allocation identity")
            expected_mode = (
                "execute"
                if event.state in ("registered", "acquiring", "acquired")
                else "cleanup"
            )
            if op.mode != expected_mode:
                raise ValueError("Resource event mode does not authorize this state")
            if event.state == "acquiring" and (
                len(event.evidence) != 1
                or event.evidence[0].content_schema != "resource-acquisition-intent/1"
                or event.evidence[0].visibility != "private"
            ):
                raise ValueError("Acquiring requires its exact private intent")
        for previous, event in zip(self.events, self.events[1:]):
            require_resource_transition(previous.state, event.state)
            if not event.evidence:
                raise ValueError("Resource transitions need attributable evidence")
        return self

    @property
    def revision(self) -> int:
        return len(self.events) - 1

    @property
    def state(self) -> ResourceState:
        return self.events[-1].state


class CleanupFailure(Contract):
    """Safe diagnostic summary; raw credentials/configuration never belong here."""

    schema_version: Literal["cleanup-failure/1"] = "cleanup-failure/1"
    component_id: Identifier
    reason_code: Identifier
    evidence: tuple[EvidenceRef, ...] = ()


class ClosureReceipt(Contract):
    """Known cleanup facts, including failure; not a training admission decision."""

    schema_version: Literal["closure-receipt/1"] = "closure-receipt/1"
    token: AllocationToken
    operation_id: Identifier
    status: Literal["closed", "failed", "unconfirmed"]
    evidence: tuple[EvidenceRef, ...]
    primary_error: CleanupFailure | None = None
    cleanup_errors: tuple[CleanupFailure, ...] = ()

    @model_validator(mode="after")
    def truthful_closure(self) -> Self:
        if self.status == "closed" and (not self.evidence or self.cleanup_errors):
            raise ValueError("Closed requires evidence and no cleanup errors")
        if self.status == "failed" and not self.cleanup_errors:
            raise ValueError("Failed cleanup requires its diagnostic")
        return self
