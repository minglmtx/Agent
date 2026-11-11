"""Complete task -> existing native Teacher part -> independent readonly review."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.application.task_teacher import (
    publish_task_teacher_attempt,
    TaskTeacherUnconfirmed,
)
from lab_generate_skill.application.task_teacher_review import (
    review_task_teacher_attempt,
)
from lab_generate_skill.bootstrap.task_teacher import completed_task_teacher_review
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.task_teacher import PublishedTaskTeacherAttempt
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.application.teacher_attempt import TeacherAttemptUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from source_review_records import ReadOnlyEvidence
from task_actor_v2_fixtures import current_task_case
from task_teacher_fixtures import completed_input, native_deps
from teacher_attempt_fixtures import UnitNativeAuthority, UnitTraceAuthority
from test_run_journal import command


def test_current_task_result_to_full_allowed_teacher_and_closed_independent_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = current_task_case(tmp_path / "current", monkeypatch)
    c = completed_input(current.task)
    task, store = c.task, c.task.admission.data.store
    close = command(
        "task-teacher-model-close", attempt=task.plan.intent.binding.attempt_id
    )
    current.native.client.close(task.deps.controls.bind(close))
    before = len(current.native.channel.sent)
    authority = UnitNativeAuthority()
    deps = native_deps(task, authority)
    published = publish_task_teacher_attempt(
        c.original, deps, control=task.deps.controls.bind(c.original.operation)
    )
    envelope = TaskAttemptResult.model_validate_json(
        store.read(c.original.result.attempt_ref)
    )
    executed = ExecutedTaskReceipt.model_validate_json(
        store.read(envelope.execution_ref)
    )
    assert published.part.source.actor_request_ref != executed.actor_request_ref
    assert store.read(published.part.source.actor_request_ref) == store.read(
        executed.actor_request_ref
    )
    assert (
        publish_task_teacher_attempt(
            c.original, deps, control=task.deps.controls.bind(c.original.operation)
        )
        == published
    )
    raw = store.read(published.part.source.allowed_view_ref)
    view = TeacherAttemptView.model_validate_json(raw)
    assert view.native["steps"] == view.native["generation_rounds"] == 1
    assert view.native["success"] is False
    assert view.native["candidate_id"] == task.phases.initialized.actor.candidate_id
    assert (
        published.part.source.attempt_id == c.original.result.intent.binding.attempt_id
    )
    assert len(current.native.channel.sent) == before
    assert (
        current.native.loader.session.calls
        == task.browser.calls
        == len(current.completed)
        == 1
    )
    assert b"task-execution-plan/1" not in raw and b"reset-receipt/1" not in raw
    assert b"closed-task-resources/1" not in raw and b"unit_feedback_only" not in raw
    authority.denied = True
    with pytest.raises(TaskTeacherUnconfirmed) as caught:
        publish_task_teacher_attempt(
            c.original, deps, control=task.deps.controls.bind(c.original.operation)
        )
    assert isinstance(caught.value.primary, TeacherAttemptUnconfirmed)
    assert isinstance(caught.value.primary.primary, PermissionError)
    assert caught.value.part is None and not caught.value.retained
    authority.denied = False
    readonly = ReadOnlyEvidence(tmp_path / "current/original-task/evidence")
    review = completed_task_teacher_review(
        readonly,
        task.deps.runs,
        task.deps.states,
        task.phases,
        EvidenceObservations(readonly, task.deps.controls),
        EvidenceTraceRecords(readonly, task.deps.controls, UnitTraceAuthority()),
        authority,
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Readonly review cannot invoke forward composer")

    import lab_generate_skill.teacher.actor_attempt as forward

    monkeypatch.setattr(forward, "actor_attempt", forbidden)
    operation = c.original.operation.cleanup(
        "task-teacher-readonly", now=datetime.now(timezone.utc), seconds=60
    )
    receipt = review_task_teacher_attempt(
        published, review, operation, control=task.deps.controls.bind(operation)
    )
    assert receipt.original == c.original and receipt.part == published.part
    assert len(current.native.channel.sent) == before and authority.calls == 4


def test_bridge_outer_ack_loss_retains_complete_part_and_readonly_recovery_without_reexecution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = current_task_case(tmp_path / "current", monkeypatch)
    c = completed_input(current.task)
    task, store = c.task, c.task.admission.data.store
    close = command(
        "outer-ack-model-close", attempt=task.plan.intent.binding.attempt_id
    )
    current.native.client.close(task.deps.controls.bind(close))
    before = len(current.native.channel.sent)
    authority = UnitNativeAuthority()
    deps = native_deps(task, authority)
    original_put = store.put

    def lose_ack(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        ref = original_put(raw, metadata, control, exchange_id=exchange_id)
        if metadata.content_schema == "task-teacher-receipt/1":
            raise OSError("unit original outer provenance acknowledgement lost")
        return ref

    monkeypatch.setattr(store, "put", lose_ack)
    with pytest.raises(TaskTeacherUnconfirmed) as caught:
        publish_task_teacher_attempt(
            c.original, deps, control=task.deps.controls.bind(c.original.operation)
        )
    error = caught.value
    assert error.phase == "task_lineage" and isinstance(error.primary, OSError)
    assert error.part is not None and len(error.retained) == 1
    published = PublishedTaskTeacherAttempt(
        receipt_ref=error.retained[0], part=error.part
    )
    readonly = ReadOnlyEvidence(tmp_path / "current/original-task/evidence")
    review = completed_task_teacher_review(
        readonly,
        task.deps.runs,
        task.deps.states,
        task.phases,
        EvidenceObservations(readonly, task.deps.controls),
        EvidenceTraceRecords(readonly, task.deps.controls, UnitTraceAuthority()),
        authority,
    )
    op = c.original.operation.cleanup(
        "outer-ack-readonly", now=datetime.now(timezone.utc), seconds=60
    )
    receipt = review_task_teacher_attempt(
        published, review, op, control=task.deps.controls.bind(op)
    )
    assert receipt.original == c.original and len(current.native.channel.sent) == before
    assert current.native.loader.session.calls == task.browser.calls == 1
