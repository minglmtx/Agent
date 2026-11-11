"""Complete original task source -> controlled Teacher -> current Actor recheck."""

from pathlib import Path
import pytest
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.errors import RevisionConflict
from lab_generate_skill.application.task_teacher import publish_task_teacher_attempt
from lab_generate_skill.application.task_teacher_review import (
    review_task_teacher_attempt,
)
from task_teacher_control_fixtures import task_teacher_control_case
from task_teacher_fixtures import completed_input, native_deps
from test_run_journal import command


def test_complete_original_task_teacher_control_revised_actor_and_closed_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_teacher_control_case(tmp_path / "case", monkeypatch)
    source, wire = c.source, c.wire
    before = source.native.loader.session.calls
    assert before == 4 and not wire.transport.calls
    step = c.step()
    revised = construct_targets(step, c.deps)
    assert revised.status == "advanced" and revised.teacher is not None
    assert revised.progress.project().next_action.kind == "execute"
    assert (
        len(wire.transport.calls) == 1 and source.native.loader.session.calls == before
    )
    response = revised.progress.project().candidates[4].response
    assert (
        isinstance(response, RevisionResult)
        and response.schema_version == "revision-result/2"
    )
    assert response.execution_ref is not None
    assert (
        TeacherRevisionPlan.model_validate_json(
            source.data.store.read(revised.teacher.bound.reference)
        )
        == revised.teacher.bound.plan
    )
    # Original completed Teacher step observes its existing logical slot, never
    # sends a second request or manufactures another revision attempt.
    with pytest.raises(RevisionConflict):
        construct_targets(step, c.deps)
    assert len(wire.transport.calls) == 1
    fifth, actor_step, deps = c.revised_actor(monkeypatch)
    actual = construct_targets(actor_step, deps)
    assert actual.status == "advanced"
    result = actual.progress.project().attempts[-1]
    assert result.intent.candidate_slot == 4
    envelope = TaskAttemptResult.model_validate_json(
        source.data.store.read(result.attempt_ref)
    )
    executed = ExecutedTaskReceipt.model_validate_json(
        source.data.store.read(envelope.execution_ref)
    )
    request = ActorRunRequest.model_validate_json(
        source.data.store.read(executed.actor_request_ref)
    )
    assert request.skill == response.skill
    assert source.native.loader.session.calls == 5 and len(wire.transport.calls) == 1
    assert (
        source.tasks[0].task.deps.runs.read(command()).project()[1][-1].stage
        == "sealed"
    )
    # Consume the known returned fact; do not reexecute a sealed task to make
    # Teacher material. Its full independent task/native/Reset proof is reused.
    known = completed_input(fifth.task, result=result)
    native = native_deps(fifth.task, source.native_authority)
    part = publish_task_teacher_attempt(
        known.original,
        native,
        control=fifth.task.deps.controls.bind(known.original.operation),
    )
    reviewed = review_task_teacher_attempt(
        part,
        source.review,
        known.original.operation,
        control=fifth.task.deps.controls.bind(known.original.operation),
    )
    assert reviewed.original.result == result
    with pytest.raises(RevisionConflict):
        construct_targets(actor_step, deps)
    assert source.native.loader.session.calls == 5 and len(wire.transport.calls) == 1
    source.native.client.close(
        source.tasks[0].task.deps.controls.bind(source.bindings.operation)
    )
