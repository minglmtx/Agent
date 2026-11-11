"""Saved original Actor work reaches Task/Actor2 judgment, close and Reset."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.application.construct_targets import (
    construct_targets,
    ConstructionStepUnconfirmed,
)
from lab_generate_skill.application.construction_task_preparation import (
    prepare_actor_step,
    ActorPreparationUnconfirmed,
)
from lab_generate_skill.bootstrap.construction_control import (
    actor_preparation_dependencies,
    construction_steps,
)
from lab_generate_skill.domain.construction_control import ExecuteConstructionWork
from lab_generate_skill.domain.construction_task_preparation import ActorPreparation
from lab_generate_skill.domain.errors import InvalidTransition, RevisionConflict
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.policies.construction_attempt import original_attempt_intent
from construction_task_preparation_fixtures import task_preparation_case
from task_teacher_control_fixtures import task_teacher_control_case
from test_run_journal import command


def test_original_candidate_saved_readonly_work_then_current_actor_closed_reset_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_preparation_case(tmp_path / "case", monkeypatch)
    task, native = c.current.task, c.current.native
    request = c.request()
    before = c.control.journal.read(request.operation)
    assert (
        original_attempt_intent(before, request.task.intent.binding.attempt_id)
        == request.task.intent
    )
    saved = prepare_actor_step(request, c.deps)
    assert saved == prepare_actor_step(request, c.deps)
    assert c.control.journal.read(request.operation) == before
    assert native.loader.session.calls == 0 and not task.phases.calls
    read = c.records.load(
        saved.reference,
        request.run,
        request.operation,
        control=c.control.controls.bind(request.operation),
    )
    assert read == saved and isinstance(read.step.work, ExecuteConstructionWork)
    actual = construct_targets(read.step, c.control)
    result = actual.progress.project().attempts[-1]
    assert result.intent == task.plan.intent and result.evaluation.status == "failure"
    envelope = TaskAttemptResult.model_validate_json(
        task.admission.data.store.read(result.attempt_ref)
    )
    assert envelope.schema_version == "attempt-result/1"
    executed = ExecutedTaskReceipt.model_validate_json(
        task.admission.data.store.read(envelope.execution_ref)
    )
    assert executed.reset_ref.content_schema == "reset-receipt/1"
    actor = ActorRunRequest.model_validate_json(
        task.admission.data.store.read(executed.actor_request_ref)
    )
    assert actor.schema_version == "actor-run-request/2"
    assert task.deps.runs.read(command()).project()[1][-1].stage == "sealed"
    assert task.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    assert native.loader.session.calls == 1
    with pytest.raises(RevisionConflict):
        construct_targets(read.step, c.control)
    cleanup = request.operation.cleanup(
        "prepared-task-read-after-close", now=datetime.now(timezone.utc), seconds=60
    )
    assert (
        c.records.load(
            saved.reference,
            request.run,
            cleanup,
            control=c.control.controls.bind(cleanup),
        )
        == saved
    )
    assert native.loader.session.calls == 1
    native.client.close(task.deps.controls.bind(cleanup))


def test_unknown_task_blocks_new_attempt_id_and_saved_step_never_reinvokes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_preparation_case(tmp_path / "case", monkeypatch)
    saved = prepare_actor_step(c.request(), c.deps)
    c.current.task.phases.errors["start"] = OSError(
        "original task start outcome unknown"
    )
    with pytest.raises(ConstructionStepUnconfirmed):
        construct_targets(saved.step, c.control)
    before = tuple(c.current.task.phases.calls)
    # A new external attempt identity still cannot bypass the old pending slot.
    request = c.request("new-id")
    intent = request.task.intent.model_copy(
        update={
            "binding": request.task.intent.binding.model_copy(
                update={"attempt_id": "another-attempt"}
            )
        }
    )
    with pytest.raises(InvalidTransition):
        original_attempt_intent(
            c.control.journal.read(request.operation), intent.binding.attempt_id
        )
    with pytest.raises(ActorPreparationUnconfirmed) as caught:
        prepare_actor_step(request, c.deps)
    assert (
        isinstance(caught.value.primary, InvalidTransition)
        and not caught.value.retained
    )
    assert construct_targets(saved.step, c.control).status == "waiting"
    assert tuple(c.current.task.phases.calls) == before
    assert c.current.native.loader.session.calls == 0


def test_completed_task_teacher_revision_uses_same_actor_preparation_and_native_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_teacher_control_case(tmp_path / "case", monkeypatch)
    revised = construct_targets(c.step(), c.deps)
    assert revised.teacher is not None
    fifth, old, control = c.revised_actor(monkeypatch)
    assert isinstance(old.work, ExecuteConstructionWork)
    request = ActorPreparation(
        run=old.run,
        expected_revision=old.expected_revision,
        task=fifth.task.plan,
        operation=old.operation,
        completion_operation=old.work.completion_operation,
    )
    data = c.source.data
    deps = actor_preparation_dependencies(control, evidence=data.store)
    saved = prepare_actor_step(request, deps)
    read = construction_steps(data.store).load(
        saved.reference,
        request.run,
        request.operation,
        control=control.controls.bind(request.operation),
    )
    assert read.step == old
    actual = construct_targets(read.step, control)
    result = actual.progress.project().attempts[-1]
    assert (
        result.intent.skill_digest
        == revised.progress.project().candidates[4].response.skill.content_digest
    )
    assert fifth.task.deps.runs.read(command()).project()[1][-1].stage == "sealed"
    assert (
        len(c.wire.transport.calls) == 1 and c.source.native.loader.session.calls == 5
    )
    c.source.native.client.close(
        fifth.task.deps.controls.bind(c.source.bindings.operation)
    )
