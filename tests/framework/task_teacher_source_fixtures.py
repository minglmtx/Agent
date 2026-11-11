"""One coherent original file history with current task/Actor2/native parts.

Physical site/browser/model/closure grants are declared unit facts. No actual
weights, website, DB or provider qualification is created by this fixture.
"""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.application.teacher_source_admission import (
    TeacherConstructionSourceDeps,
)
from lab_generate_skill.application.task_teacher_inputs import TaskTeacherReadDeps
from lab_generate_skill.application.task_teacher_review import TaskTeacherReviewDeps
from lab_generate_skill.application.task_teacher import publish_task_teacher_attempt
from lab_generate_skill.bootstrap.teacher_attempt import native_teacher_attempt_review
from lab_generate_skill.bootstrap.teacher_source_admission import (
    qualified_task_teacher_source,
)
from lab_generate_skill.bootstrap.teacher_source import teacher_source_dependencies
from lab_generate_skill.domain.construction import (
    AttemptCompleted,
    ProgressEvent,
    ConstructionPlan,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.teacher_source import TeacherSourceBindings
from lab_generate_skill.domain.task_teacher import (
    TaskTeacherInput,
    PublishedTaskTeacherAttempt,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import OwnershipConflict
from actor_admission_fixtures import fixture as admission_case
from construction_storage_fixtures import StorageFixture, UnitConstructionAuthority
from task_execution_fixtures import TaskCase, task_case
from task_execution_construction_fixtures import UnitExecutedTaskAuthority
from task_actor_v2_fixtures import current_task_case, CurrentTaskCase
from task_teacher_fixtures import completed_input, native_deps
from teacher_attempt_fixtures import UnitNativeAuthority, UnitTraceAuthority
from source_actor_context_fixtures import source_context_case
from actor_long_fixtures import long_config
from test_run_journal import command


class UnitCompleteTaskAuthority(UnitConstructionAuthority):
    def __init__(self, original: UnitConstructionAuthority) -> None:
        super().__init__(original.store)
        self.original = original
        self.tasks: dict[str, TaskCase] = {}
        self.denied = False

    def verify_plan(self, plan: ConstructionPlan, operation: OperationContext) -> None:
        if self.denied:
            raise OwnershipConflict("Unit full task source denied")
        self.original.verify_plan(plan, operation)

    def verify_event(
        self,
        progress: ConstructionProgress,
        event: ProgressEvent,
        operation: OperationContext,
    ) -> None:
        self.verify_plan(progress.plan, operation)
        if isinstance(event, AttemptCompleted):
            case = self.tasks[event.result.intent.binding.attempt_id]
            UnitExecutedTaskAuthority(case).verify_event(progress, event, operation)
        else:
            self.original.verify_event(progress, event, operation)


class UnitClosedTasks:
    def __init__(self, tasks: dict[str, TaskCase]) -> None:
        self.tasks = tasks

    def verify(
        self,
        plan: TaskExecutionPlan,
        progress: ConstructionProgress,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        self.tasks[plan.intent.binding.attempt_id].phases.verify(
            plan, progress, snapshot, reset, control
        )

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.tasks[plan.intent.binding.attempt_id].phases.verify_closed(
            plan, closed, operation, control
        )


@dataclass
class CompleteTaskSourceCase:
    data: StorageFixture
    tasks: tuple[CurrentTaskCase, ...]
    originals: tuple[TaskTeacherInput, ...]
    parts: tuple[PublishedTaskTeacherAttempt, ...]
    progress: ConstructionProgress
    bindings: TeacherSourceBindings
    review: TaskTeacherReviewDeps
    original_source: TeacherConstructionSourceDeps
    native_authority: UnitNativeAuthority
    native: Any

    def authority(self, operation: OperationContext) -> Any:
        return qualified_task_teacher_source(
            self.data.plan.run, self.original_source, self.review, operation
        )

    def deps(self) -> Any:
        controls = self.tasks[0].task.deps.controls
        return teacher_source_dependencies(
            self.data.store,
            EvidenceObservations(self.data.store, controls),
            EvidenceRetrievalRecords(
                self.data.store, controls, self.data.retrieval_authority
            ),
            self.authority(self.bindings.operation),
        )


def complete_task_source_case(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    count: int = 4,
    source_seconds: int = 60,
    recorded_teacher: bool = False,
) -> CompleteTaskSourceCase:
    assert count in (4, 5, 6)
    root.mkdir()
    native = source_context_case(
        root / "shared-native", monkeypatch, engine_config=long_config()
    )
    tasks: list[CurrentTaskCase] = []
    original_inputs: list[TaskTeacherInput] = []
    data: StorageFixture | None = None
    authority: UnitCompleteTaskAuthority | None = None

    for slot in range(count):

        def build(path: Path) -> TaskCase:
            if data is None:
                return task_case(path)
            path.mkdir()
            prepared = admission_case(
                path,
                stage="planned",
                allowed_actions=("send_msg_to_user",),
                shared_data=data,
            )
            return task_case(path, admitted=prepared, shared_run=tasks[0].task)

        current = current_task_case(
            root / ("task-" + str(slot)),
            monkeypatch,
            shared_native=native,
            task_builder=build,
            recorded_teacher=recorded_teacher,
        )
        if data is None:
            data = current.task.admission.data
            if recorded_teacher:
                from teacher_assembly_fixtures import UnitNativeConstructionAuthority

                authority = UnitCompleteTaskAuthority(
                    UnitNativeConstructionAuthority(data.store)
                )
            else:
                authority = UnitCompleteTaskAuthority(data.authority)
            # Explicit fixture output-variant verifier; no frozen record is edited.
            data.authority = authority
        assert authority is not None and data is not None
        authority.tasks[current.task.plan.intent.binding.attempt_id] = current.task
        assert current.task.plan.intent.candidate_slot == slot
        completed = completed_input(current.task)
        tasks.append(current)
        original_inputs.append(completed.original)
        journal = data.journal()
        before = journal.read(command())
        event = AttemptCompleted(
            operation=command("complete-native-task-" + str(slot)),
            result=completed.original.result,
        )
        journal.append(event, before.revision, event.operation)

    assert data is not None and authority is not None
    first = tasks[0].task
    control = first.deps.controls
    operation = command("complete-task-teacher-round-" + str(count - 3))
    if source_seconds != 60:
        # Choose the material-read deadline before first binding/publication.
        operation = operation.model_copy(
            update={
                "deadline": datetime.now(timezone.utc)
                + timedelta(seconds=source_seconds)
            }
        )
    native_authority = UnitNativeAuthority()
    parts = []
    originals = []
    for task, original in zip(tasks, original_inputs, strict=True):
        # Declare this allowed projection command before publication; never alter
        # the original result, Actor request, trace, stage or closure records.
        declared = TaskTeacherInput.model_validate(
            {**original.model_dump(), "operation": operation}
        )
        deps = native_deps(task.task, native_authority)
        parts.append(
            publish_task_teacher_attempt(
                declared, deps, control=control.bind(operation)
            )
        )
        originals.append(declared)
    reads = TaskTeacherReadDeps(
        data.store, first.deps.runs, first.deps.states, UnitClosedTasks(authority.tasks)
    )
    review = TaskTeacherReviewDeps(
        reads,
        native_teacher_attempt_review(
            data.store,
            EvidenceObservations(data.store, control),
            EvidenceTraceRecords(data.store, control, UnitTraceAuthority()),
            native_authority,
        ),
    )
    instructions = data.store.put(
        b"Use every complete original attempt; preserve unknown results.",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="teacher-instructions/1",
            visibility="teacher",
            producer="unit-complete-task-source",
        ),
    )
    bindings = TeacherSourceBindings(
        schema_version="teacher-source-bindings/2",
        request_id="complete-task-teacher-request-" + str(count - 3),
        operation=operation,
        teacher_round=count - 3,
        instructions_ref=instructions,
        attempts=tuple(p.part.source for p in parts),
        task_receipt_refs=tuple(p.receipt_ref for p in parts),
    )
    source_deps = TeacherConstructionSourceDeps(
        data.journal(),
        first.deps.runs,
        data.claims(),
        EvidenceContextRecords(data.store, control, data.context_authority),
        EvidenceRunPlans(data.store, control),
        authority,
    )
    progress = data.journal().read(command())
    return CompleteTaskSourceCase(
        data,
        tuple(tasks),
        tuple(originals),
        tuple(parts),
        progress,
        bindings,
        review,
        source_deps,
        native_authority,
        native,
    )
