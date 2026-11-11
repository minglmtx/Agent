"""One original Task4/Teacher/Task5/selection; all physical/world grants are unit.

The review evaluator rereads separate predeclared unit world facts and reuses
the original unit evaluator implementation; it never returns worker judgments.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal, cast
import pytest
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.application.construction_task_preparation import (
    prepare_actor_step,
)
from lab_generate_skill.application.review_run import ReviewDeps, ReviewEvaluator
from lab_generate_skill.application.task_teacher import publish_task_teacher_attempt
from lab_generate_skill.bootstrap.construction_control import (
    actor_preparation_dependencies,
)
from lab_generate_skill.bootstrap.construction_review import (
    construction_review_dependencies,
    completed_teacher_review_service,
)
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    SelectConstructionWork,
    ExecuteConstructionWork,
)
from lab_generate_skill.domain.construction_task_preparation import ActorPreparation
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.evaluation import Evaluation, EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.review import ReviewPlan, ReviewTask, ReviewTeacher
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.application.teacher_actor_reads import canonical
from task_teacher_control_fixtures import (
    TaskTeacherControlCase,
    task_teacher_control_case,
)
from task_actor_v2_fixtures import CurrentTaskCase
from task_execution_fixtures import UnitPhases
from task_teacher_fixtures import completed_input, native_deps
from construction_storage_fixtures import put
from test_run_journal import command


class UnitWorld(Contract):
    schema_version: Literal["unit-review-world/1"] = "unit-review-world/1"
    statuses: dict[str, Literal["success", "failure", "unknown"]]


class UnitReplayEvaluator(UnitPhases):
    def __init__(self, reference: EvidenceRef) -> None:
        self.reference = reference
        self.reads = 0

    def hit(self, name: str, control: OperationControl) -> None:
        control.checkpoint()
        assert name == "evaluate"
        self.reads += 1

    def evaluate(
        self, contract: EvaluationContract, evidence: object, control: OperationControl
    ) -> Evaluation:
        facts = canonical(
            self.reference,
            "unit-review-world/1",
            UnitWorld,
            cast(EvidenceReader, evidence),
            control,
        )
        self.evaluation_status = facts.statuses[contract.attempt_id]
        return super().evaluate(contract, evidence, control)


class UnitReviewAuthority:
    denied = False

    def __init__(self) -> None:
        self.calls = 0

    def verify(
        self,
        plan: ReviewPlan,
        original: RunPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if (
            self.denied
            or plan.run.plan_ref != plan.original_run_plan_ref
            or original.release_ref != plan.judgment_release
        ):
            raise OwnershipConflict("Unit recorded review read/runtime denied")


@dataclass
class ReviewCase:
    control: TaskTeacherControlCase
    fifth: CurrentTaskCase
    sealed: ConstructionProgress
    source_ref: EvidenceRef
    teacher: Any
    parts: tuple[Any, ...]
    world: EvidenceRef
    authority: UnitReviewAuthority

    def plan(self, name: str = "first", *, now: datetime | None = None) -> ReviewPlan:
        c = self.control
        # New readonly operations, not changed source/send/settlement identities.
        now = datetime.now(timezone.utc) if now is None else now
        op = command("construction-independent-review-" + name).model_copy(
            update={"deadline": now + timedelta(seconds=180)}
        )
        tasks = []
        for slot, part in enumerate(self.parts):
            original = (
                c.source.originals[slot].operation
                if slot < 4
                else self.fifth_original_operation
            )
            read = original.cleanup(
                "review-original-task-" + name + "-" + str(slot), now=now, seconds=60
            )
            tasks.append(ReviewTask(published=part, operation=read))
        teacher_read = self.teacher.bound.plan.send.operation.cleanup(
            "review-original-teacher-" + name, now=now, seconds=60
        )
        selection = self.sealed.project().selection
        assert selection is not None
        selected = next(
            (
                r
                for r in self.sealed.project().attempts
                if r.intent.binding.attempt_id == selection.attempt_id
            ),
            None,
        )
        return ReviewPlan(
            review_id="original-construction-review-" + name,
            run=self.sealed.plan.run,
            original_run_plan_ref=self.sealed.plan.run.plan_ref,
            sealed_evidence_ref=self.source_ref,
            original_execution_release=self.sealed.plan.run.release_ref,
            judgment_release=self.sealed.plan.run.release_ref,
            selection=selection,
            selected_evaluation_ref=selected.evaluation_ref if selected else None,
            tasks=tuple(tasks),
            teachers=(ReviewTeacher(published=self.teacher, operation=teacher_read),),
            operation=op,
        )

    @property
    def fifth_original_operation(self) -> OperationContext:
        from lab_generate_skill.domain.task_teacher import TaskTeacherReceipt

        return TaskTeacherReceipt.model_validate_json(
            self.control.source.data.store.read(self.parts[-1].receipt_ref)
        ).original.operation

    def deps(self, plan: ReviewPlan) -> ReviewDeps:
        c, s = self.control, self.control.source
        controls = self.fifth.task.deps.controls
        service = completed_teacher_review_service(
            plan.teachers[0],
            self.sealed,
            c.wire.review,
            counts=c.wire.count_review,
            controls=controls,
            enclosing=controls.bind(plan.operation),
        )
        original = s.original_source
        return construction_review_dependencies(
            plan,
            self.sealed,
            evidence=s.data.store,
            plans=original.plans,
            journal=c.deps.journal,
            recorded_authority=original.original,
            contexts=original.contexts,
            retrieval=c.wire.review.source.retrieval,
            claims=original.claims,
            tasks=s.review,
            evaluators=tuple(
                ReviewEvaluator(
                    t.published.part.source.attempt_id, UnitReplayEvaluator(self.world)
                )
                for t in plan.tasks
            ),
            teachers=(service,),
            authority=self.authority,
            controls=controls,
        )


def construction_review_case(root: Path, monkeypatch: pytest.MonkeyPatch) -> ReviewCase:
    c = task_teacher_control_case(root, monkeypatch)
    store = c.source.data.store
    # Explicit unit environment outcomes before the fifth execution/review.
    world = put(
        store,
        UnitWorld.model_validate(
            {
                "statuses": {
                    **{"attempt-" + str(i): "failure" for i in range(4)},
                    "attempt-4": "success",
                }
            }
        ),
        "unit-review-world/1",
    )
    changed = construct_targets(c.step(), c.deps)
    assert changed.teacher is not None
    fifth, legacy, deps = c.revised_actor(monkeypatch)
    assert isinstance(legacy.work, ExecuteConstructionWork)
    fifth.task.phases.evaluation_status = "success"
    request = ActorPreparation(
        run=legacy.run,
        expected_revision=legacy.expected_revision,
        task=fifth.task.plan,
        operation=legacy.operation,
        completion_operation=legacy.work.completion_operation,
    )
    prepared = prepare_actor_step(
        request, actor_preparation_dependencies(deps, evidence=store)
    )
    executed = construct_targets(prepared.step, deps)
    result = executed.progress.project().attempts[-1]
    known = completed_input(fifth.task, result=result)
    part = publish_task_teacher_attempt(
        known.original,
        native_deps(fifth.task, c.source.native_authority),
        control=deps.controls.bind(known.original.operation),
    )
    selected = construct_targets(
        ConstructionStepPlan(
            run=legacy.run,
            expected_revision=executed.progress.revision,
            operation=command("original-final-selection"),
            work=SelectConstructionWork(),
        ),
        deps,
    )
    assert selected.status == "complete"
    source_ref = put(store, selected.progress, "construction-progress/1")
    close = c.source.bindings.operation.cleanup(
        "native-closed-before-construction-review",
        now=datetime.now(timezone.utc),
        seconds=60,
    )
    c.source.native.client.close(deps.controls.bind(close))
    return ReviewCase(
        c,
        fifth,
        selected.progress,
        source_ref,
        changed.teacher,
        (*c.source.parts, part),
        world,
        UnitReviewAuthority(),
    )
