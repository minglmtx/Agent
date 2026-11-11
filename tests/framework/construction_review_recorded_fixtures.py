"""Fresh-process unit read assembly, only persisted original refs and file logs.

Every permission below is explicitly a unit grant. It cannot qualify a real
release, website, model, closure or training target. No case/runner is unpickled.
"""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.adapters.models.openrouter_request import prepare_openrouter
from lab_generate_skill.application.teacher_actor_reads import canonical
from lab_generate_skill.application.task_teacher_inputs import TaskTeacherReadDeps
from lab_generate_skill.application.task_teacher_review import TaskTeacherReviewDeps
from lab_generate_skill.application.teacher_source_admission import (
    TeacherConstructionSourceDeps,
)
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.application.teacher_assembly_review import (
    TeacherAssemblyReviewDeps,
)
from lab_generate_skill.application.teacher_transaction_review import (
    construction_snapshot_read,
)
from lab_generate_skill.application.review_run import ReviewDeps, ReviewEvaluator
from lab_generate_skill.bootstrap.construction_review import (
    construction_review_dependencies,
    completed_teacher_review_service,
)
from lab_generate_skill.bootstrap.teacher_source_admission import (
    qualified_task_teacher_source,
)
from lab_generate_skill.bootstrap.teacher_source import teacher_source_authority
from lab_generate_skill.bootstrap.teacher_attempt import native_teacher_attempt_review
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.adapters.models.teacher_request_binding import (
    verify_teacher_wire_parameters,
)
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.review import ReviewPlan, ReviewTask, ReviewTeacher
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    ProgressEvent,
    AttemptCompleted,
)
from lab_generate_skill.domain.construction_journal import ConstructionCapacity
from lab_generate_skill.domain.task_teacher import TaskTeacherReceipt
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.task_execution import ClosedTaskResources
from lab_generate_skill.domain.model_request import ResolvedModelRequest
from lab_generate_skill.domain.teacher_assembly import (
    TeacherRevisionAssemblyInput,
    TeacherRevisionAssemblyReceipt,
)
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_control_fixtures import EvidenceFixtureStore
from construction_review_fixtures import (
    ReviewCase,
    UnitReviewAuthority,
    UnitReplayEvaluator,
)
from task_execution_fixtures import TaskCase, UnitPhases
from task_execution_construction_fixtures import UnitExecutedTaskAuthority
from task_teacher_source_fixtures import UnitClosedTasks
from teacher_assembly_fixtures import (
    UnitNativeConstructionAuthority,
    UnitAssemblyAuthority,
)
from teacher_revision_fixtures import WholeWireReview
from teacher_attempt_fixtures import UnitNativeAuthority, UnitTraceAuthority
from state_storage_fixtures import UnitStateAuthority
from context_storage_fixtures import UnitContextAuthority
from test_retrieval_evidence import UnitAuthority as UnitRetrievalAuthority
from context_preparation_fixtures import (
    UnitAuthority as UnitContextPreparationAuthority,
)
from claim_fixtures import UnitClaimAuthority
from test_run_journal import CancelSwitch


class UnitReviewBundle(Contract):
    schema_version: Literal["unit-recorded-construction-review/1"] = (
        "unit-recorded-construction-review/1"
    )
    template: ReviewPlan
    cas_root: str
    claims_root: str
    run_root: str
    construction_root: str
    construction_capacity: ConstructionCapacity
    world_ref: EvidenceRef


def recorded_bundle(c: ReviewCase, plan: ReviewPlan) -> UnitReviewBundle:
    data = c.control.source.data
    runs = c.fifth.task.deps.runs
    assert isinstance(runs, FileRunJournal)
    construction = c.control.deps.journal
    assert isinstance(construction, FileConstructionJournal)
    return UnitReviewBundle(
        template=plan,
        cas_root=str(data.store._blobs.parent),
        claims_root=str(data.root / "claims"),
        run_root=str(runs._root),
        construction_root=str(construction.file.root),
        construction_capacity=construction.capacity,
        world_ref=c.world,
    )


class ReadonlyUnitStore(EvidenceFixtureStore):
    def put(
        self,
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        raise AssertionError("Fresh independent review cannot write original CAS")


class UnitRecordedConstructionAuthority(UnitNativeConstructionAuthority):
    def __init__(self, store: ReadonlyUnitStore, tasks: dict[str, TaskCase]) -> None:
        super().__init__(store)
        self.tasks = tasks

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        if isinstance(event, AttemptCompleted):
            UnitExecutedTaskAuthority(
                self.tasks[event.result.intent.binding.attempt_id]
            ).verify_event(progress, event, op)
        else:
            super().verify_event(progress, event, op)


def recorded_wire_counts(
    store: ReadonlyUnitStore, bound: TeacherRevisionPlan, control: OperationControl
) -> WholeWireReview:
    raw_params = store.read(bound.send.parameters_ref, control)

    def wire(raw: bytes, model: str) -> bytes:
        request = bound.send.reservation.request.model_copy(
            update={"input_sha256": hashlib.sha256(raw).hexdigest(), "model_id": model}
        )
        return prepare_openrouter(
            ResolvedModelRequest(
                request=request,
                input_bytes=raw,
                parameters_bytes=raw_params,
                limits=bound.send.limits,
            )
        )

    return WholeWireReview(store, wire)


def read_recorded_bundle(bundle: UnitReviewBundle) -> tuple[ReviewPlan, ReviewDeps]:
    controls = OperationGuards(SystemClock(), CancelSwitch())
    store = ReadonlyUnitStore(Path(bundle.cas_root), initialize=False)
    now = datetime.now(timezone.utc)
    base = bundle.template
    root_op = base.operation.model_copy(
        update={
            "operation_id": "fresh-process-review",
            "deadline": now + timedelta(seconds=180),
        }
    )
    outer = controls.bind(root_op)
    items = []
    for i, t in enumerate(base.tasks):
        receipt = canonical(
            t.published.receipt_ref,
            "task-teacher-receipt/1",
            TaskTeacherReceipt,
            store,
            outer,
            512 * 1024,
        )
        items.append(
            ReviewTask(
                published=t.published,
                operation=receipt.original.operation.cleanup(
                    "fresh-recorded-task-" + str(i), now=now, seconds=60
                ),
            )
        )
    teachers = tuple(
        ReviewTeacher(
            published=t.published,
            operation=t.published.bound.plan.send.operation.cleanup(
                "fresh-recorded-teacher-" + str(i), now=now, seconds=60
            ),
        )
        for i, t in enumerate(base.teachers)
    )
    plan = ReviewPlan.model_validate(
        {
            **base.model_dump(),
            "review_id": "independent-process-original-review",
            "operation": root_op,
            "tasks": tuple(items),
            "teachers": teachers,
        }
    )
    sealed = canonical(
        plan.sealed_evidence_ref,
        "construction-progress/1",
        ConstructionProgress,
        store,
        outer,
        8 * 1024**2,
    )
    plans = EvidenceRunPlans(store, controls)
    original = plans.load(plan.run, root_op)
    runs = FileRunJournal(
        Path(bundle.run_root), plan.run, controls, store, capacity=original.run_capacity
    )
    states = EvidenceStateRecords(store, controls, UnitStateAuthority())
    contexts = EvidenceContextRecords(store, controls, UnitContextAuthority())
    retrieval = EvidenceRetrievalRecords(store, controls, UnitRetrievalAuthority(store))
    claims = FileSourceClaims(
        Path(bundle.claims_root),
        "unit-scope",
        controls,
        store,
        plans,
        UnitClaimAuthority(),
    )
    native_base = UnitNativeConstructionAuthority(store)
    tasks: dict[str, TaskCase] = {}
    for item in items:
        receipt = canonical(
            item.published.receipt_ref,
            "task-teacher-receipt/1",
            TaskTeacherReceipt,
            store,
            outer,
            512 * 1024,
        )
        envelope = canonical(
            receipt.original.result.attempt_ref,
            "attempt-result/1",
            TaskAttemptResult,
            store,
            outer,
        )
        executed = canonical(
            envelope.execution_ref,
            "executed-task-receipt/1",
            ExecutedTaskReceipt,
            store,
            outer,
        )
        closed = canonical(
            executed.closed_ref,
            "closed-task-resources/1",
            ClosedTaskResources,
            store,
            outer,
        )
        phases = object.__new__(UnitPhases)
        phases.calls, phases.errors, phases.closed, phases.closure_denied = (
            [],
            {},
            closed,
            False,
        )
        # The existing unit verifier only needs these read ports. No live Task
        # runner, model, browser or preparation instance is reconstructed.
        task = SimpleNamespace(
            admission=SimpleNamespace(
                data=SimpleNamespace(store=store, authority=native_base)
            ),
            deps=SimpleNamespace(states=states, runs=runs),
            phases=phases,
        )
        tasks[receipt.original.result.intent.binding.attempt_id] = cast(TaskCase, task)
    recorded = UnitRecordedConstructionAuthority(store, tasks)
    journal = FileConstructionJournal(
        Path(bundle.construction_root),
        sealed.plan,
        bundle.construction_capacity,
        controls,
        store,
        plans,
        recorded,
        contexts,
        retrieval,
        claims,
    )
    task_review = TaskTeacherReviewDeps(
        TaskTeacherReadDeps(store, runs, states, UnitClosedTasks(tasks)),
        native_teacher_attempt_review(
            store,
            EvidenceObservations(store, controls),
            EvidenceTraceRecords(store, controls, UnitTraceAuthority()),
            UnitNativeAuthority(),
        ),
    )
    services = []
    for teacher in teachers:
        op, published = teacher.operation, teacher.published
        snapshot = construction_snapshot_read(sealed, op, controls, outer)
        assembly_receipt = canonical(
            published.receipt_ref,
            "teacher-revision-assembly/1",
            TeacherRevisionAssemblyReceipt,
            store,
            outer,
            256 * 1024,
        )
        assembly_input = canonical(
            assembly_receipt.input_ref,
            "teacher-revision-assembly-input/1",
            TeacherRevisionAssemblyInput,
            store,
            outer,
            2 * 1024**2,
        )
        source_deps = TeacherConstructionSourceDeps(
            snapshot, runs, claims, contexts, plans, recorded
        )
        source = qualified_task_teacher_source(plan.run, source_deps, task_review, op)
        observations = EvidenceObservations(store, controls)
        source_review = TeacherSourceReviewDeps(
            store, observations, retrieval, source, op
        )
        context = teacher_source_authority(
            UnitContextPreparationAuthority(),
            assembly_input.source,
            evidence=store,
            observations=observations,
            retrieval=retrieval,
            authority=source,
            operation=op,
        )
        bound = published.bound.plan
        counts = recorded_wire_counts(store, bound, outer)
        project, protect = build_teacher_context(bound.preparation.policy)
        reviewed = TeacherAssemblyReviewDeps(
            store,
            snapshot,
            plans,
            source_review,
            ContextReviewDeps(store, context, project, protect, counts),
            UnitAssemblyAuthority(),
            verify_teacher_wire_parameters,
        )
        services.append(
            completed_teacher_review_service(
                teacher,
                sealed,
                reviewed,
                counts=counts,
                controls=controls,
                enclosing=outer,
            )
        )
    deps = construction_review_dependencies(
        plan,
        sealed,
        evidence=store,
        plans=plans,
        journal=journal,
        recorded_authority=recorded,
        contexts=contexts,
        retrieval=retrieval,
        claims=claims,
        tasks=task_review,
        evaluators=tuple(
            ReviewEvaluator(
                t.published.part.source.attempt_id,
                UnitReplayEvaluator(bundle.world_ref),
            )
            for t in items
        ),
        teachers=tuple(services),
        authority=UnitReviewAuthority(),
        controls=controls,
    )
    return plan, deps
