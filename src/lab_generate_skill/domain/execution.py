"""Run/attempt histories and pure transition rules; no scheduling or I/O.

Inputs: frozen bindings, explicit operations and attributable stage evidence.
Outputs: immutable validated histories. Append functions compare revisions and
support identical-event replay; callers still need a transactional RunJournal.
No return value grants a submission, Actor retry, resource takeover or training
permission. Sealed means this history is immutable, not that cleanup succeeded.
"""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .errors import InvalidTransition, OwnershipConflict, RevisionConflict
from .evidence import EvidenceRef
from .identity import TaskIdentity
from .lifecycle import OperationContext, ResourceOwner
from .validation import Contract, Identifier, NonEmptyText

RunStage = Literal[
    "planned",
    "validated",
    "claimed",
    "submitting",
    "submission_uncertain",
    "confirmed_not_submitted",
    "submitted",
    "running",
    "closing",
    "sealed",
]
AttemptStage = Literal[
    "planned",
    "acquiring",
    "preparing",
    "starting",
    "baseline_verified",
    "executing",
    "captured",
    "evaluated",
    "closing",
    "restoring",
    "sealed",
]
StopReason = Literal["blocked", "cancelled", "timeout", "error"]


class ExecutionFailure(Contract):
    """Safe diagnostic, not raw configuration or a task-failure judgment."""

    schema_version: Literal["execution-failure/1"] = "execution-failure/1"
    component_id: Identifier
    reason_code: Identifier
    message: NonEmptyText
    evidence: tuple[EvidenceRef, ...] = ()


class RunBinding(Contract):
    """Stable owner, plan, release and scheduler key committed before submit."""

    schema_version: Literal["run-binding/1"] = "run-binding/1"
    owner: ResourceOwner
    plan_ref: EvidenceRef
    release_ref: EvidenceRef
    submission_key: Identifier


class AttemptBinding(Contract):
    """One claimed task attempt under the original frozen run binding."""

    schema_version: Literal["attempt-binding/1"] = "attempt-binding/1"
    run: RunBinding
    attempt_id: Identifier
    task: TaskIdentity
    claim_ref: EvidenceRef


class SubmissionObservation(Contract):
    """Scheduler facts; not-submitted must be proven, not inferred from absence.

    The scheduler adapter/reviewer verifies evidence semantics. This contract
    checks identity/shape only; a caller cannot use construction as authority.
    """

    schema_version: Literal["submission-observation/1"] = "submission-observation/1"
    submission_key: Identifier
    outcome: Literal["accepted", "uncertain", "confirmed_not_submitted"]
    job_ids: tuple[Identifier, ...] = ()
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def job_identity(self) -> Self:
        if len(set(self.job_ids)) != len(self.job_ids):
            raise ValueError("Scheduler job IDs must be unique")
        if (self.outcome == "accepted") != bool(self.job_ids):
            raise ValueError("Only accepted submission carries confirmed job IDs")
        return self


class StageEvent(Contract):
    """Shared event fields; use RunEvent or AttemptEvent at public boundaries.

    occurred_at is an aware audit timestamp, not a lease/ordering authority.
    predecessor operation IDs determine order even when clocks move backwards.
    """

    previous_operation_id: Identifier | None = None
    operation: OperationContext
    occurred_at: AwareDatetime
    component_id: Identifier
    job_id: Identifier | None = None
    worker_id: Identifier | None = None
    node_id: Identifier | None = None
    inputs: tuple[EvidenceRef, ...] = ()
    outputs: tuple[EvidenceRef, ...] = ()
    stop_reason: StopReason | None = None
    primary_error: ExecutionFailure | None = None
    cleanup_errors: tuple[ExecutionFailure, ...] = ()

    @model_validator(mode="after")
    def diagnostics(self) -> Self:
        if self.primary_error is not None and self.stop_reason is None:
            raise ValueError("Primary error requires an explicit stop reason")
        if self.stop_reason == "error" and self.primary_error is None:
            raise ValueError("Error stop requires its original diagnostic")
        if self.cleanup_errors and self.operation.mode != "cleanup":
            raise ValueError("Cleanup errors belong to cleanup operations")
        return self


class RunEvent(StageEvent):
    schema_version: Literal["run-event/1"] = "run-event/1"
    stage: RunStage
    submission: SubmissionObservation | None = None


class AttemptEvent(StageEvent):
    schema_version: Literal["attempt-event/1"] = "attempt-event/1"
    stage: AttemptStage


def require_run_transition(before: RunStage, after: RunStage) -> None:
    """Uncertain submission cannot become submitting without proven absence."""
    edges: dict[RunStage, frozenset[RunStage]] = {
        "planned": frozenset(("validated", "closing")),
        "validated": frozenset(("claimed", "closing")),
        "claimed": frozenset(("submitting", "closing")),
        "submitting": frozenset(("submitted", "submission_uncertain")),
        "submission_uncertain": frozenset(
            ("submitted", "confirmed_not_submitted", "closing")
        ),
        "confirmed_not_submitted": frozenset(("submitting", "closing")),
        "submitted": frozenset(("running", "closing")),
        "running": frozenset(("closing",)),
        "closing": frozenset(("sealed",)),
        "sealed": frozenset(),
    }
    if after not in edges.get(before, frozenset()):
        raise InvalidTransition(f"Run cannot transition from {before} to {after}")


def require_attempt_transition(before: AttemptStage, after: AttemptStage) -> None:
    """Early stops still pass through closing/restoring before diagnostic seal."""
    edges: dict[AttemptStage, frozenset[AttemptStage]] = {
        "planned": frozenset(("acquiring", "closing")),
        "acquiring": frozenset(("preparing", "closing")),
        "preparing": frozenset(("starting", "closing")),
        "starting": frozenset(("baseline_verified", "closing")),
        "baseline_verified": frozenset(("executing", "closing")),
        "executing": frozenset(("captured", "closing")),
        "captured": frozenset(("evaluated", "closing")),
        "evaluated": frozenset(("closing",)),
        "closing": frozenset(("restoring",)),
        "restoring": frozenset(("sealed",)),
        "sealed": frozenset(),
    }
    if after not in edges.get(before, frozenset()):
        raise InvalidTransition(f"Attempt cannot transition from {before} to {after}")


def _validate_events(
    events: tuple[RunEvent | AttemptEvent, ...],
    owner: ResourceOwner,
    attempt_id: str | None,
) -> None:
    """Common chain/identity checks; source timestamps do not define causality."""
    seen: set[str] = set()
    previous: str | None = None
    stop: StopReason | None = None
    primary: ExecutionFailure | None = None
    for index, event in enumerate(events):
        op = event.operation
        if (
            op.run_id != owner.run_id
            or op.owner_id != owner.owner_id
            or op.attempt_id != attempt_id
        ):
            raise ValueError("Event operation must retain original run/owner/attempt")
        if op.operation_id in seen or event.previous_operation_id != previous:
            raise ValueError("Event predecessor or operation identity is invalid")
        if index == 0:
            if (
                event.stage != "planned"
                or event.stop_reason is not None
                or event.cleanup_errors
            ):
                raise ValueError("History must start at an unstopped planned event")
        elif not event.outputs:
            raise ValueError(
                "Every stage transition requires attributable output evidence"
            )
        cleanup = event.stage in ("closing", "restoring", "sealed")
        if (op.mode == "cleanup") != cleanup:
            raise ValueError("Operation mode must match execution or cleanup stage")
        if stop is not None and not cleanup:
            raise ValueError("Stopped execution cannot start new work")
        if event.stop_reason is not None:
            if not cleanup:
                raise ValueError("Stop is recorded when entering or continuing cleanup")
            if stop is not None and event.stop_reason != stop:
                raise ValueError("The original stop reason cannot be replaced")
            stop = event.stop_reason
        if event.primary_error is not None:
            if primary is not None and event.primary_error != primary:
                raise ValueError("The original primary error cannot be replaced")
            primary = event.primary_error
        seen.add(op.operation_id)
        previous = op.operation_id


class RunRecord(Contract):
    """Complete append-only logical history; sealed is not a success judgment."""

    schema_version: Literal["run-record/1"] = "run-record/1"
    binding: RunBinding
    events: tuple[RunEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def history(self) -> Self:
        _validate_events(self.events, self.binding.owner, None)
        for index, event in enumerate(self.events):
            expected: str | None = {
                "submitted": "accepted",
                "submission_uncertain": "uncertain",
                "confirmed_not_submitted": "confirmed_not_submitted",
            }.get(event.stage)
            if expected is None:
                if event.submission is not None:
                    raise ValueError(
                        "Submission facts belong to submission outcome stages"
                    )
            elif (
                event.submission is None
                or event.submission.outcome != expected
                or event.submission.submission_key != self.binding.submission_key
                or any(ref not in event.outputs for ref in event.submission.evidence)
            ):
                raise ValueError(
                    "Submission outcome requires matching key and output evidence"
                )
            if index:
                before = self.events[index - 1].stage
                require_run_transition(before, event.stage)
                if (
                    event.stage == "closing"
                    and before != "running"
                    and event.stop_reason is None
                ):
                    raise ValueError(
                        "Early run closure requires an explicit stop reason"
                    )
        return self

    @property
    def revision(self) -> int:
        return len(self.events) - 1

    @property
    def stage(self) -> RunStage:
        return self.events[-1].stage

    @property
    def stop_reason(self) -> StopReason | None:
        return next(
            (
                event.stop_reason
                for event in self.events
                if event.stop_reason is not None
            ),
            None,
        )

    @property
    def primary_error(self) -> ExecutionFailure | None:
        return next(
            (
                event.primary_error
                for event in self.events
                if event.primary_error is not None
            ),
            None,
        )

    @property
    def cleanup_errors(self) -> tuple[ExecutionFailure, ...]:
        return tuple(error for event in self.events for error in event.cleanup_errors)


class AttemptRecord(Contract):
    """Attempt progression is independent of Evaluation/review/export outcomes."""

    schema_version: Literal["attempt-record/1"] = "attempt-record/1"
    binding: AttemptBinding
    events: tuple[AttemptEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def history(self) -> Self:
        _validate_events(self.events, self.binding.run.owner, self.binding.attempt_id)
        for before, after in zip(self.events, self.events[1:]):
            require_attempt_transition(before.stage, after.stage)
            if (
                after.stage == "closing"
                and before.stage != "evaluated"
                and after.stop_reason is None
            ):
                raise ValueError(
                    "Early attempt closure requires an explicit stop reason"
                )
        return self

    @property
    def revision(self) -> int:
        return len(self.events) - 1

    @property
    def stage(self) -> AttemptStage:
        return self.events[-1].stage

    @property
    def stop_reason(self) -> StopReason | None:
        return next(
            (
                event.stop_reason
                for event in self.events
                if event.stop_reason is not None
            ),
            None,
        )

    @property
    def primary_error(self) -> ExecutionFailure | None:
        return next(
            (
                event.primary_error
                for event in self.events
                if event.primary_error is not None
            ),
            None,
        )

    @property
    def cleanup_errors(self) -> tuple[ExecutionFailure, ...]:
        return tuple(error for event in self.events for error in event.cleanup_errors)


def _is_replay(
    events: tuple[RunEvent, ...] | tuple[AttemptEvent, ...],
    event: RunEvent | AttemptEvent,
    expected_revision: int,
) -> bool:
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected revision must be a nonnegative integer")
    for previous in events:
        if previous.operation.operation_id == event.operation.operation_id:
            if previous != event:
                raise OwnershipConflict("Operation ID already binds another event")
            return True
    if expected_revision != len(events) - 1:
        raise RevisionConflict("Execution history revision changed")
    return False


def append_run_event(
    record: RunRecord, event: RunEvent, expected_revision: int
) -> RunRecord:
    """Pure checked append; replay returns current history, never submit permission."""
    if _is_replay(record.events, event, expected_revision):
        return record
    return RunRecord(binding=record.binding, events=(*record.events, event))


def append_attempt_event(
    record: AttemptRecord, event: AttemptEvent, expected_revision: int
) -> AttemptRecord:
    """Pure checked append; never overwrites prior evidence or restarts an Actor."""
    if _is_replay(record.events, event, expected_revision):
        return record
    return AttemptRecord(binding=record.binding, events=(*record.events, event))
