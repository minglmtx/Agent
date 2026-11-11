"""Original completed task and explicit synthetic native/closure authorities.

The current-v2 combination uses actual native count/generate/once frames over a
unit engine. No physical source, website, real weight or provider qualification.
"""

from lab_generate_skill.application.construction_task_result import (
    construction_task_result,
)

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.task_teacher import TaskTeacherDeps
from lab_generate_skill.application.task_teacher_inputs import TaskTeacherReadDeps
from lab_generate_skill.bootstrap.task_teacher import completed_task_teacher
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.domain.task_teacher import TaskTeacherInput
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.teacher_attempt import TeacherFeedbackPolicy
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.construction import ConstructionAttemptResult
from task_execution_fixtures import TaskCase, task_case
from teacher_attempt_fixtures import UnitNativeAuthority, UnitTraceAuthority
from test_run_journal import command


@dataclass(frozen=True)
class TaskTeacherCase:
    task: TaskCase
    original: TaskTeacherInput
    reads: TaskTeacherReadDeps


def completed_input(
    task: TaskCase, *, result: ConstructionAttemptResult | None = None
) -> TaskTeacherCase:
    if result is None:
        returned = construction_task_result(execute_task(task.plan, task.deps))
        assert isinstance(returned, ConstructionAttemptResult)
        result = returned
    store = task.admission.data.store
    authorization = store.put(
        b'{"unit_feedback_only":true}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-feedback-authorization/1",
            visibility="private",
            producer="unit-task-teacher-feedback",
        ),
    )
    scope = task.phases.initialized.actor.scope
    original = TaskTeacherInput(
        result=result,
        scope=TeacherContextScope(
            owner=scope.owner, task=scope.task, context_id=scope.context_id
        ),
        feedback=TeacherFeedbackPolicy(
            policy_id="unit-original-check-policy",
            authorization_ref=authorization,
            check_names=tuple(c.name for c in result.evaluation.checks),
        ),
        operation=command("original-task-teacher-part"),
    )
    return TaskTeacherCase(
        task,
        original,
        TaskTeacherReadDeps(store, task.deps.runs, task.deps.states, task.phases),
    )


def completed_case(root: Path) -> TaskTeacherCase:
    return completed_input(task_case(root))


def native_deps(task: TaskCase, authority: UnitNativeAuthority) -> TaskTeacherDeps:
    store, controls = task.admission.data.store, task.deps.controls
    return completed_task_teacher(
        store,
        task.deps.runs,
        task.deps.states,
        task.phases,
        EvidenceObservations(store, controls),
        EvidenceTraceRecords(store, controls, UnitTraceAuthority()),
        authority,
    )
