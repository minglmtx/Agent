"""A known Teacher return remains reconcilable after its original send deadline."""

from datetime import timedelta
from pathlib import Path
import time
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.application.construct_targets import (
    construct_targets,
    ConstructionStepUnconfirmed,
)
from lab_generate_skill.domain.construction_control import RecordConstructionWork
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from task_teacher_control_fixtures import task_teacher_control_case
from test_task_teacher_control_boundaries import bind, FailedCompletionJournal


def test_known_return_reconciles_with_fresh_read_cleanup_after_original_settlement_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_teacher_control_case(tmp_path / "case", monkeypatch)
    error = OSError("known response could not be appended by original writer")

    def broken(proof: TeacherConstructionVerifier) -> ConstructionJournal:
        return FailedCompletionJournal(
            c.source.data.journal(teacher_review=proof), error
        )

    with pytest.raises(ConstructionStepUnconfirmed) as caught:
        construct_targets(c.step(), bind(c, journal_with_review=broken))
    known = caught.value
    assert (
        known.primary is error
        and known.teacher is not None
        and isinstance(known.event, CallCompleted)
    )
    assert known.response is not None and len(c.wire.transport.calls) == 1
    plan = known.teacher.bound.plan
    c.source.native.client.close(c.deps.controls.bind(c.source.bindings.operation))
    future = plan.send.settlement_operation.deadline + timedelta(seconds=1)
    delta = (future - SystemClock().utcnow()).total_seconds()
    later_monotonic = time.monotonic() + delta
    reconcile = known.event.operation.cleanup(
        "late-known-Teacher-fact", now=future, seconds=60
    )
    read_operation = plan.send.operation.cleanup(
        "late-Teacher-proof-read", now=future, seconds=60
    )
    step = c.step().model_copy(
        update={
            "expected_revision": known.progress.revision,
            "operation": reconcile,
            "work": RecordConstructionWork(event=known.event, teacher=known.teacher),
        }
    )
    with monkeypatch.context() as clock:
        clock.setattr(SystemClock, "utcnow", lambda self: future)
        clock.setattr(SystemClock, "monotonic", lambda self: later_monotonic)
        with pytest.raises(OperationStopped):
            c.deps.controls.bind(plan.send.settlement_operation).checkpoint()
        # Read-only reconciliation must never depend on renewing the send or
        # provider settlement. The actual original response and ledger fact stay.
        wrong = bind(
            c,
            read_operation=read_operation.model_copy(
                update={"parent_operation_id": "foreign-send"}
            ),
        )
        assert wrong.teacher_journal is not None
        with pytest.raises(ValueError):
            wrong.teacher_journal(known.teacher)
        actual = construct_targets(step, bind(c, read_operation=read_operation))
        assert (
            actual.status == "advanced"
            and actual.progress.project().pending_call is None
        )
    assert (
        len(c.wire.transport.calls) == 1 and c.source.native.loader.session.calls == 4
    )
