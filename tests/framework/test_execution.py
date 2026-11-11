"""Execution contracts from design 6.1: normal, stop, uncertain and replay paths.

These are pure transition tests, not evidence of scheduler RPCs or durable CAS.
Expected edges are explicit specification fixtures independent of production code.
"""

from lab_generate_skill.ports.lifecycle import OperationControl

from datetime import datetime, timedelta, timezone
from itertools import product
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import (
    AttemptBinding,
    AttemptEvent,
    AttemptRecord,
    AttemptStage,
    ExecutionFailure,
    RunBinding,
    RunEvent,
    RunRecord,
    RunStage,
    SubmissionObservation,
    append_attempt_event,
    append_run_event,
    require_attempt_transition,
    require_run_transition,
)
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
RUN_STAGES: tuple[RunStage, ...] = (
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
)
ATTEMPT_STAGES: tuple[AttemptStage, ...] = (
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
)
RUN_EDGES = {
    ("planned", "validated"),
    ("planned", "closing"),
    ("validated", "claimed"),
    ("validated", "closing"),
    ("claimed", "submitting"),
    ("claimed", "closing"),
    ("submitting", "submitted"),
    ("submitting", "submission_uncertain"),
    ("submission_uncertain", "submitted"),
    ("submission_uncertain", "confirmed_not_submitted"),
    ("submission_uncertain", "closing"),
    ("confirmed_not_submitted", "submitting"),
    ("confirmed_not_submitted", "closing"),
    ("submitted", "running"),
    ("submitted", "closing"),
    ("running", "closing"),
    ("closing", "sealed"),
}
ATTEMPT_EDGES = set(zip(ATTEMPT_STAGES, ATTEMPT_STAGES[1:])) | {
    (stage, "closing") for stage in ATTEMPT_STAGES[:7]
}


@pytest.fixture
def proof() -> EvidenceRef:
    return EvidenceRef(
        uri="cas://sha256/" + "a" * 64,
        sha256="a" * 64,
        size_bytes=0,
        media_type="application/json",
        content_schema="fixture/1",
        visibility="private",
        producer="test",
    )


@pytest.fixture
def binding(proof: EvidenceRef, control: OperationControl | None = None) -> RunBinding:
    return RunBinding(
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id="controller", worker_id="worker"
        ),
        plan_ref=proof,
        release_ref=proof,
        submission_key="stable-key",
    )


@pytest.fixture
def attempt_binding(binding: RunBinding, proof: EvidenceRef) -> AttemptBinding:
    return AttemptBinding(
        run=binding,
        attempt_id="attempt",
        claim_ref=proof,
        task=TaskIdentity(
            source_task_id="source",
            task_id="task",
            split="train",
            site="map",
            family="export",
            contract_version=1,
        ),
    )


def operation(
    name: str, previous: str | None, *, attempt: bool, cleanup: bool
) -> OperationContext:
    return OperationContext(
        operation_id=name,
        run_id="run",
        owner_id="owner",
        attempt_id="attempt" if attempt else None,
        deadline=NOW + timedelta(minutes=5),
        mode="cleanup" if cleanup else "execute",
        parent_operation_id=previous if cleanup else None,
    )


def run_event(
    stage: RunStage,
    proof: EvidenceRef,
    previous: RunEvent | None = None,
    *,
    name: str | None = None,
) -> RunEvent:
    parent = previous.operation.operation_id if previous else None
    observation: SubmissionObservation | None = None
    if stage in ("submitted", "submission_uncertain", "confirmed_not_submitted"):
        observation = SubmissionObservation.model_validate(
            {
                "submission_key": "stable-key",
                "outcome": {
                    "submitted": "accepted",
                    "submission_uncertain": "uncertain",
                    "confirmed_not_submitted": "confirmed_not_submitted",
                }[stage],
                "job_ids": ("job-1",) if stage == "submitted" else (),
                "evidence": (proof,),
            }
        )
    return RunEvent(
        stage=stage,
        previous_operation_id=parent,
        operation=operation(
            name or stage, parent, attempt=False, cleanup=stage in ("closing", "sealed")
        ),
        occurred_at=NOW,
        component_id="controller",
        outputs=(proof,) if previous else (),
        submission=observation,
    )


def attempt_event(
    stage: AttemptStage, proof: EvidenceRef, previous: AttemptEvent | None = None
) -> AttemptEvent:
    parent = previous.operation.operation_id if previous else None
    return AttemptEvent(
        stage=stage,
        previous_operation_id=parent,
        operation=operation(
            stage,
            parent,
            attempt=True,
            cleanup=stage in ("closing", "restoring", "sealed"),
        ),
        occurred_at=NOW,
        component_id="attempt.runner",
        outputs=(proof,) if previous else (),
    )


def run_prefix(
    binding: RunBinding, proof: EvidenceRef, stages: tuple[RunStage, ...]
) -> RunRecord:
    record = RunRecord(binding=binding, events=(run_event("planned", proof),))
    for stage in stages:
        record = append_run_event(
            record, run_event(stage, proof, record.events[-1]), record.revision
        )
    return record


@pytest.mark.parametrize(("before", "after"), list(product(RUN_STAGES, RUN_STAGES)))
def test_run_transition_matrix(before: RunStage, after: RunStage) -> None:
    if (before, after) in RUN_EDGES:
        require_run_transition(before, after)
    else:
        with pytest.raises(InvalidTransition):
            require_run_transition(before, after)


@pytest.mark.parametrize(
    ("before", "after"), list(product(ATTEMPT_STAGES, ATTEMPT_STAGES))
)
def test_attempt_transition_matrix(before: AttemptStage, after: AttemptStage) -> None:
    if (before, after) in ATTEMPT_EDGES:
        require_attempt_transition(before, after)
    else:
        with pytest.raises(InvalidTransition):
            require_attempt_transition(before, after)


def test_normal_run_and_attempt_round_trip_without_success_inference(
    binding: RunBinding, attempt_binding: AttemptBinding, proof: EvidenceRef
) -> None:
    run = run_prefix(
        binding,
        proof,
        (
            "validated",
            "claimed",
            "submitting",
            "submitted",
            "running",
            "closing",
            "sealed",
        ),
    )
    attempt = AttemptRecord(
        binding=attempt_binding, events=(attempt_event("planned", proof),)
    )
    for stage in ATTEMPT_STAGES[1:]:
        attempt = append_attempt_event(
            attempt, attempt_event(stage, proof, attempt.events[-1]), attempt.revision
        )
    assert run.stage == attempt.stage == "sealed"
    assert RunRecord.model_validate_json(run.model_dump_json()) == run
    assert AttemptRecord.model_validate_json(attempt.model_dump_json()) == attempt
    assert run.binding == binding and attempt.binding == attempt_binding
    assert run.stop_reason is None and attempt.stop_reason is None
    assert "reward" not in attempt.model_dump() and "success" not in run.model_dump()
    with pytest.raises(ValidationError):
        setattr(attempt, "events", ())


def test_uncertain_submit_requires_proof_before_retry(
    binding: RunBinding, proof: EvidenceRef
) -> None:
    record = run_prefix(
        binding, proof, ("validated", "claimed", "submitting", "submission_uncertain")
    )
    with pytest.raises(ValidationError):
        append_run_event(
            record,
            run_event("submitting", proof, record.events[-1], name="retry"),
            record.revision,
        )
    assert record.stage == "submission_uncertain"
    absent = append_run_event(
        record,
        run_event("confirmed_not_submitted", proof, record.events[-1]),
        record.revision,
    )
    retry = run_event("submitting", proof, absent.events[-1], name="retry")
    resumed = append_run_event(absent, retry, absent.revision)
    assert resumed.binding.submission_key == record.binding.submission_key
    assert resumed.events[: len(record.events)] == record.events
    accepted = append_run_event(
        resumed, run_event("submitted", proof, retry), resumed.revision
    )
    assert accepted.events[-1].submission is not None
    assert accepted.events[-1].submission.job_ids == ("job-1",)


def test_uncertain_can_reconcile_existing_job_without_resubmit(
    binding: RunBinding, proof: EvidenceRef
) -> None:
    record = run_prefix(
        binding,
        proof,
        ("validated", "claimed", "submitting", "submission_uncertain", "submitted"),
    )
    assert sum(e.stage == "submitting" for e in record.events) == 1


@pytest.mark.parametrize(
    "stage", ["submitted", "submission_uncertain", "confirmed_not_submitted"]
)
@pytest.mark.parametrize("fault", ["missing", "wrong_key", "unlinked_evidence"])
def test_submission_outcome_requires_correlated_facts(
    binding: RunBinding, proof: EvidenceRef, stage: RunStage, fault: str
) -> None:
    record = run_prefix(binding, proof, ("validated", "claimed", "submitting"))
    if stage == "confirmed_not_submitted":
        record = append_run_event(
            record,
            run_event("submission_uncertain", proof, record.events[-1]),
            record.revision,
        )
    event = run_event(stage, proof, record.events[-1])
    data = event.model_dump()
    if fault == "missing":
        data["submission"] = None
    elif fault == "wrong_key":
        assert event.submission is not None
        data["submission"] = {
            **event.submission.model_dump(),
            "submission_key": "foreign",
        }
    else:
        data["outputs"] = (
            EvidenceRef.model_validate(
                {
                    **proof.model_dump(),
                    "sha256": "b" * 64,
                    "uri": "cas://sha256/" + "b" * 64,
                }
            ),
        )
    with pytest.raises(ValidationError):
        append_run_event(record, RunEvent.model_validate(data), record.revision)


@pytest.mark.parametrize(
    ("outcome", "jobs"),
    [
        ("accepted", ()),
        ("accepted", ("job", "job")),
        ("uncertain", ("job",)),
        ("confirmed_not_submitted", ("job",)),
        ("unknown", ()),
    ],
)
def test_submission_invalid_job_facts(
    proof: EvidenceRef, outcome: str, jobs: tuple[str, ...]
) -> None:
    with pytest.raises(ValidationError):
        SubmissionObservation.model_validate(
            dict(submission_key="key", outcome=outcome, job_ids=jobs, evidence=(proof,))
        )


@pytest.mark.parametrize("reason", ["blocked", "cancelled", "timeout", "error"])
def test_partial_attempt_stop_preserves_errors_through_failed_cleanup(
    attempt_binding: AttemptBinding, proof: EvidenceRef, reason: str
) -> None:
    record = AttemptRecord(
        binding=attempt_binding, events=(attempt_event("planned", proof),)
    )
    for stage in ("acquiring", "preparing"):
        record = append_attempt_event(
            record,
            attempt_event(cast(AttemptStage, stage), proof, record.events[-1]),
            record.revision,
        )
    primary = ExecutionFailure(
        component_id="site.prepare",
        reason_code="PREPARE_STOPPED",
        message="Prepare did not complete",
    )
    closing = AttemptEvent.model_validate(
        {
            **attempt_event("closing", proof, record.events[-1]).model_dump(),
            "stop_reason": reason,
            "primary_error": primary,
        }
    )
    stopped = append_attempt_event(record, closing, record.revision)
    cleanup_failure = ExecutionFailure(
        component_id="site.restore",
        reason_code="RESET_FAILED",
        message="Restore did not complete",
    )
    restoring = AttemptEvent.model_validate(
        {
            **attempt_event("restoring", proof, closing).model_dump(),
            "cleanup_errors": (cleanup_failure,),
        }
    )
    restored = append_attempt_event(stopped, restoring, stopped.revision)
    sealed = append_attempt_event(
        restored, attempt_event("sealed", proof, restoring), restored.revision
    )
    assert sealed.stop_reason == reason
    assert sealed.primary_error == primary
    assert sealed.cleanup_errors == (cleanup_failure,)
    assert sealed.events[: len(record.events)] == record.events
    assert "executing" not in [event.stage for event in sealed.events]


@pytest.mark.parametrize(
    "field,value", [("stop_reason", "timeout"), ("primary_error", None)]
)
def test_stop_diagnostic_cannot_be_replaced(
    attempt_binding: AttemptBinding, proof: EvidenceRef, field: str, value: object
) -> None:
    first = attempt_event("planned", proof)
    error = ExecutionFailure(
        component_id="prepare", reason_code="ERROR", message="original"
    )
    close = AttemptEvent.model_validate(
        {
            **attempt_event("closing", proof, first).model_dump(),
            "stop_reason": "error",
            "primary_error": error,
        }
    )
    record = AttemptRecord(binding=attempt_binding, events=(first, close))
    data = attempt_event("restoring", proof, close).model_dump()
    data.update(stop_reason="error", primary_error=error)
    data[field] = value
    with pytest.raises(ValidationError):
        append_attempt_event(record, AttemptEvent.model_validate(data), record.revision)
    changed = ExecutionFailure(
        component_id="other", reason_code="OTHER", message="replacement"
    )
    data.update(stop_reason="error", primary_error=changed)
    with pytest.raises(ValidationError):
        append_attempt_event(record, AttemptEvent.model_validate(data), record.revision)


@pytest.mark.parametrize("kind", ["run", "attempt"])
def test_early_closing_needs_stop_reason(
    binding: RunBinding, attempt_binding: AttemptBinding, proof: EvidenceRef, kind: str
) -> None:
    if kind == "run":
        first = run_event("planned", proof)
        with pytest.raises(ValidationError):
            RunRecord(
                binding=binding, events=(first, run_event("closing", proof, first))
            )
    else:
        start = attempt_event("planned", proof)
        with pytest.raises(ValidationError):
            AttemptRecord(
                binding=attempt_binding,
                events=(start, attempt_event("closing", proof, start)),
            )


@pytest.mark.parametrize("revision", [None, True, False, "0", 0.0, -1, [], {}])
def test_revision_wrong_type_and_range(
    binding: RunBinding, proof: EvidenceRef, revision: object
) -> None:
    record = run_prefix(binding, proof, ())
    with pytest.raises(ValueError):
        append_run_event(
            record,
            run_event("validated", proof, record.events[-1]),
            cast(int, revision),
        )


def test_replay_stale_revision_conflict_and_terminal_no_reopen(
    binding: RunBinding, proof: EvidenceRef
) -> None:
    prior = run_prefix(binding, proof, ())
    event = run_event("validated", proof, prior.events[-1])
    record = append_run_event(prior, event, 0)
    assert append_run_event(record, event, 0) is record
    changed = RunEvent.model_validate(
        {**event.model_dump(), "component_id": "different"}
    )
    with pytest.raises(OwnershipConflict):
        append_run_event(record, changed, 0)
    with pytest.raises(RevisionConflict):
        append_run_event(record, run_event("claimed", proof, event), 0)
    sealed = run_prefix(
        binding,
        proof,
        (
            "validated",
            "claimed",
            "submitting",
            "submitted",
            "running",
            "closing",
            "sealed",
        ),
    )
    assert append_run_event(sealed, sealed.events[1], 0) is sealed
    with pytest.raises(ValidationError):
        append_run_event(
            sealed,
            run_event("submitting", proof, sealed.events[-1], name="reopen"),
            sealed.revision,
        )


@pytest.mark.parametrize(
    "field,value",
    [("run_id", "foreign"), ("owner_id", "foreign"), ("attempt_id", "foreign")],
)
def test_event_cannot_change_execution_identity(
    binding: RunBinding, proof: EvidenceRef, field: str, value: str
) -> None:
    first = run_event("planned", proof)
    event = run_event("validated", proof, first)
    data = event.model_dump()
    data["operation"] = {**event.operation.model_dump(), field: value}
    with pytest.raises(ValidationError):
        RunRecord(binding=binding, events=(first, RunEvent.model_validate(data)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("previous_operation_id", None),
        ("previous_operation_id", "wrong"),
        ("outputs", ()),
        ("occurred_at", NOW.replace(tzinfo=None)),
        ("stage", "success"),
        ("schema_version", "run-event/99"),
        ("unknown_field", 1),
    ],
)
def test_event_boundary_rejects_invalid_chain_schema_and_evidence(
    binding: RunBinding, proof: EvidenceRef, field: str, value: object
) -> None:
    first = run_event("planned", proof)
    data = run_event("validated", proof, first).model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        RunRecord(binding=binding, events=(first, RunEvent.model_validate(data)))


@pytest.mark.parametrize("events", [(), None, [], "", ({},)])
def test_empty_and_malformed_histories(binding: RunBinding, events: object) -> None:
    with pytest.raises(ValidationError):
        RunRecord.model_validate(dict(binding=binding, events=events))


def test_predecessors_not_wall_clock_define_order(
    binding: RunBinding, proof: EvidenceRef
) -> None:
    record = run_prefix(binding, proof, ())
    event = RunEvent.model_validate(
        {
            **run_event("validated", proof, record.events[-1]).model_dump(),
            "occurred_at": NOW - timedelta(days=1),
        }
    )
    assert append_run_event(record, event, record.revision).stage == "validated"


def test_attempt_replay_conflict_stale_revision_and_sealed_history(
    attempt_binding: AttemptBinding,
    proof: EvidenceRef,
) -> None:
    record = AttemptRecord(
        binding=attempt_binding, events=(attempt_event("planned", proof),)
    )
    acquired = attempt_event("acquiring", proof, record.events[-1])
    record = append_attempt_event(record, acquired, 0)
    assert append_attempt_event(record, acquired, 0) is record
    with pytest.raises(OwnershipConflict):
        append_attempt_event(
            record,
            AttemptEvent.model_validate(
                {**acquired.model_dump(), "component_id": "different"}
            ),
            0,
        )
    with pytest.raises(RevisionConflict):
        append_attempt_event(record, attempt_event("preparing", proof, acquired), 0)
    for stage in ATTEMPT_STAGES[2:]:
        record = append_attempt_event(
            record, attempt_event(stage, proof, record.events[-1]), record.revision
        )
    assert append_attempt_event(record, acquired, 0) is record
    reused = attempt_event("executing", proof, record.events[-1])
    # Reusing the old executing ID is an identity conflict, before state checks.
    with pytest.raises(OwnershipConflict):
        append_attempt_event(
            record,
            reused,
            record.revision,
        )
    # A fresh operation reaches the distinct sealed-state rejection boundary.
    reopen = AttemptEvent.model_validate(
        {
            **reused.model_dump(),
            "operation": {**reused.operation.model_dump(), "operation_id": "reopen"},
        }
    )
    with pytest.raises(ValidationError):
        append_attempt_event(record, reopen, record.revision)


@pytest.mark.parametrize(
    "field,value",
    [("run_id", "foreign"), ("owner_id", "foreign"), ("attempt_id", None)],
)
def test_attempt_identity_must_match_original_binding(
    attempt_binding: AttemptBinding,
    proof: EvidenceRef,
    field: str,
    value: object,
) -> None:
    first = attempt_event("planned", proof)
    event = attempt_event("acquiring", proof, first)
    data = event.model_dump()
    data["operation"] = {**event.operation.model_dump(), field: value}
    with pytest.raises(ValidationError):
        AttemptRecord(
            binding=attempt_binding, events=(first, AttemptEvent.model_validate(data))
        )


@pytest.mark.parametrize("kind", ["run", "attempt"])
def test_cleanup_operation_cannot_start_execution(
    binding: RunBinding,
    attempt_binding: AttemptBinding,
    proof: EvidenceRef,
    kind: str,
) -> None:
    if kind == "run":
        first = run_event("planned", proof)
        event = run_event("validated", proof, first)
        data = event.model_dump()
        data["operation"] = {
            **event.operation.model_dump(),
            "mode": "cleanup",
            "parent_operation_id": "planned",
        }
        with pytest.raises(ValidationError):
            RunRecord(binding=binding, events=(first, RunEvent.model_validate(data)))
    else:
        start = attempt_event("planned", proof)
        acquired = attempt_event("acquiring", proof, start)
        data = acquired.model_dump()
        data["operation"] = {
            **acquired.operation.model_dump(),
            "mode": "cleanup",
            "parent_operation_id": "planned",
        }
        with pytest.raises(ValidationError):
            AttemptRecord(
                binding=attempt_binding,
                events=(start, AttemptEvent.model_validate(data)),
            )


def test_diagnostic_seal_preserves_unresolved_submission(
    binding: RunBinding, proof: EvidenceRef
) -> None:
    record = run_prefix(
        binding, proof, ("validated", "claimed", "submitting", "submission_uncertain")
    )
    closing = RunEvent.model_validate(
        {
            **run_event("closing", proof, record.events[-1]).model_dump(),
            "stop_reason": "timeout",
        }
    )
    record = append_run_event(record, closing, record.revision)
    sealed = append_run_event(
        record, run_event("sealed", proof, closing), record.revision
    )
    assert sealed.stop_reason == "timeout"
    facts = [
        event.submission for event in sealed.events if event.submission is not None
    ]
    assert len(facts) == 1 and facts[0].outcome == "uncertain"
    assert not any(event.stage == "confirmed_not_submitted" for event in sealed.events)
