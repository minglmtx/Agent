"""One original full task history reaches original Teacher/controlled Actor.

Every physical/provider/count grant is an explicit unit fact. Frozen original
records are never relabeled; no actual weights, website, DB or API is invoked.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.application.teacher_source import publish_teacher_source
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.application.teacher_assembly_plan import original_teacher_plan
from lab_generate_skill.bootstrap.construction_control import (
    construction_control_dependencies,
)
from lab_generate_skill.bootstrap.construction_teacher import (
    completed_task_teacher_dependencies,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.domain.teacher_source import TeacherSourceReceipt
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    ReviseConstructionWork,
    ExecuteConstructionWork,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.ports.construction import ConstructionJournal
from actor_admission_fixtures import fixture as admission_case
from task_execution_fixtures import TaskCase, task_case
from task_actor_v2_fixtures import CurrentTaskCase, current_task_case
from task_teacher_source_fixtures import (
    CompleteTaskSourceCase,
    UnitCompleteTaskAuthority,
    complete_task_source_case,
)
from teacher_assembly_fixtures import (
    AssemblySourceData,
    SourceAssemblyCase,
    assembly_from_source,
)
from test_construction_state import planned_attempt
from test_run_journal import command


@dataclass
class TaskTeacherControlCase:
    root: Path
    source: CompleteTaskSourceCase
    wire: SourceAssemblyCase[CompleteTaskSourceCase]
    deps: ConstructionDeps

    def step(self) -> ConstructionStepPlan:
        original = self.wire.original
        op = original.preparation.operation
        return ConstructionStepPlan(
            run=self.source.data.plan.run,
            expected_revision=self.deps.journal.read(op).revision,
            operation=op,
            work=ReviseConstructionWork(
                original=original,
                completion_operation=op.cleanup(
                    "completed-task-teacher-result",
                    now=datetime.now(timezone.utc),
                    seconds=60,
                ),
            ),
        )

    def revised_actor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[CurrentTaskCase, ConstructionStepPlan, ConstructionDeps]:
        c = self.source
        old = self.deps.journal.read(command())
        assert old.project().next_action.kind == "execute"
        planned = planned_attempt(old)

        def build(root: Path) -> TaskCase:
            root.mkdir()
            admission = admission_case(
                root,
                stage="planned",
                allowed_actions=("send_msg_to_user",),
                shared_data=c.data,
                register_attempt=False,
            )
            return task_case(root, admitted=admission, shared_run=c.tasks[0].task)

        fifth = current_task_case(
            self.root / "revised-task",
            monkeypatch,
            shared_native=c.native,
            task_builder=build,
            recorded_teacher=True,
        )
        assert fifth.task.plan.intent == planned.intent
        assert isinstance(c.data.authority, UnitCompleteTaskAuthority)
        c.data.authority.tasks[planned.intent.binding.attempt_id] = fifth.task
        assert self.deps.journal.read(command()) == old
        step = ConstructionStepPlan(
            run=old.plan.run,
            expected_revision=old.revision,
            operation=planned.operation,
            work=ExecuteConstructionWork(
                planned=planned,
                invoke_operation=fifth.task.plan.operation,
                completion_operation=planned.operation.cleanup(
                    "completed-task-revised-actor-result",
                    now=datetime.now(timezone.utc),
                    seconds=60,
                ),
            ),
        )
        deps = replace(
            self.deps,
            attempts=RecordedConstructionTask(fifth.task.plan, fifth.task.deps),
        )
        return fifth, step, deps


def task_teacher_control_case(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> TaskTeacherControlCase:
    root.mkdir()
    c = complete_task_source_case(
        root / "tasks", monkeypatch, source_seconds=240, recorded_teacher=True
    )
    # This new request is declared before its first source publication. All
    # previous task results, traces, closures and source operations stay exact.
    c.bindings = c.bindings.model_copy(
        update={"request_id": "original-native-revision-completed-task1"}
    )
    op = c.bindings.operation
    controls = c.tasks[0].task.deps.controls
    initial_review = TeacherSourceReviewDeps(
        c.data.store,
        EvidenceObservations(c.data.store, controls),
        EvidenceRetrievalRecords(c.data.store, controls, c.data.retrieval_authority),
        c.authority(op),
        op,
    )
    published = publish_teacher_source(
        c.progress, c.bindings, c.deps(), control=controls.bind(op)
    )
    material = AssemblySourceData(
        c.data,
        c.progress,
        op,
        c.bindings,
        published,
        controls,
        initial_review.observations,
        initial_review.retrieval,
        initial_review.authority,
        lambda operation: (
            initial_review
            if operation == op
            else TeacherSourceReviewDeps(
                c.data.store,
                initial_review.observations,
                initial_review.retrieval,
                c.authority(operation),
                operation,
            )
        ),
    )
    directory = root / "teacher"
    directory.mkdir()
    wire = assembly_from_source(directory, c, material)
    # Same frozen plan as original assembly, declared before the unit send.
    receipt = TeacherSourceReceipt.model_validate_json(
        c.data.store.read(published.receipt_ref)
    )
    wire.send_authority.expected = original_teacher_plan(
        c.progress, receipt, wire.original
    )[0]
    base = construction_control_dependencies(
        wire.deps.journal,
        controls,
        readiness=ConstructionReadiness(
            c.original_source.runs,
            c.original_source.claims,
            c.original_source.plans,
            c.original_source.original,
        ),
    )

    def journal(proof: TeacherConstructionVerifier) -> ConstructionJournal:
        return c.data.journal(teacher_review=proof)

    deps = completed_task_teacher_dependencies(
        base,
        wire.deps,
        wire.review,
        ledger=wire.ledger,
        transport=wire.transport,
        send_authority=wire.send_authority,
        counts=wire.count_review,
        read_operation=wire.original.settlement_operation,
        journal_with_review=journal,
    )
    return TaskTeacherControlCase(root, c, wire, deps)
