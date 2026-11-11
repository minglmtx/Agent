"""Original file journals/roles; explicit synthetic lifecycle/physical rights."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.bootstrap.construction_control import (
    construction_control_dependencies,
)
from lab_generate_skill.bootstrap.teacher_assembly import assembled_teacher
from lab_generate_skill.bootstrap.teacher_revision import recorded_teacher_review
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.domain.construction import (
    AttemptIntent,
    ConstructionAttemptResult,
    AttemptCompleted,
)
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    ReviseConstructionWork,
    ExecuteConstructionWork,
)
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.execution import AttemptStage
from lab_generate_skill.domain.run_journal import AttemptEntry
from lab_generate_skill.ports.teacher import Teacher
from lab_generate_skill.ports.construction import ConstructionJournal
from teacher_assembly_fixtures import assembly_case, AssemblyCase
from teacher_source_admission_fixtures import admit_native_source, SourceAdmissionCase
from test_construction_state import planned_attempt
from test_run_journal import command


class UnitAttemptLifecycle:
    def __init__(self, source: SourceAdmissionCase) -> None:
        self.source = source
        self.calls: list[AttemptIntent] = []
        self.error: BaseException | None = None
        self.status = "success"

    def execute(
        self, intent: AttemptIntent, operation: OperationContext
    ) -> ConstructionAttemptResult:
        c = self.source
        assert operation.attempt_id == intent.binding.attempt_id
        self.calls.append(intent)
        if self.error is not None:
            raise self.error
        progress = c.deps.construction.read(command())
        assert progress.project().pending_attempt == intent
        result = c.native.data.event(progress, status=self.status)
        assert isinstance(result, AttemptCompleted)
        snapshot = c.runs.read(command())
        stages: tuple[AttemptStage, ...] = (
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
        for stage in stages:
            original = c.harness.attempt_entry(
                snapshot, intent.binding.attempt_id, stage
            )
            entry = AttemptEntry(binding=intent.binding, event=original.event)
            snapshot = c.runs.append(entry, snapshot.revision, entry.event.operation)
        return result.result


@dataclass
class ControlCase:
    native: AssemblyCase
    source: SourceAdmissionCase
    deps: ConstructionDeps
    attempts: UnitAttemptLifecycle
    publications: list[PublishedTeacherRevisionAssembly]

    def teacher_step(self) -> ConstructionStepPlan:
        original = self.native.original
        return ConstructionStepPlan(
            run=self.native.source.data.plan.run,
            expected_revision=self.native.deps.journal.read(
                original.preparation.operation
            ).revision,
            operation=original.preparation.operation,
            work=ReviseConstructionWork(
                original=original,
                completion_operation=original.preparation.operation.cleanup(
                    "controlled-teacher-completed",
                    now=datetime.now(timezone.utc),
                    seconds=60,
                ),
            ),
        )

    def actor_step(self) -> ConstructionStepPlan:
        current = self.deps.journal.read(command())
        planned = planned_attempt(current)
        return ConstructionStepPlan(
            run=current.plan.run,
            expected_revision=current.revision,
            operation=planned.operation,
            work=ExecuteConstructionWork(
                planned=planned,
                invoke_operation=command(
                    "controlled-actor-invocation",
                    attempt=planned.intent.binding.attempt_id,
                ),
                completion_operation=planned.operation.cleanup(
                    "controlled-actor-completed",
                    now=datetime.now(timezone.utc),
                    seconds=60,
                ),
            ),
        )


def control_case(root: Path) -> ControlCase:
    c = assembly_case(root)
    source = admit_native_source(c.source, construction=c.deps.journal)
    publications: list[PublishedTeacherRevisionAssembly] = []

    def teacher(published: PublishedTeacherRevisionAssembly) -> Teacher:
        publications.append(published)
        c.send_authority.expected = published.bound.plan
        return assembled_teacher(
            published,
            c.review,
            c.original.preparation.policy,
            ledger=c.ledger,
            transport=c.transport,
            evidence=c.source.data.store,
            controls=c.source.controls,
            source_authority=c.send_authority,
            context_authority=c.context,
            counts=c.count_review,
            runs=source.runs,
            claims=source.deps.claims,
        )

    def journal(published: PublishedTeacherRevisionAssembly) -> ConstructionJournal:
        plans = EvidenceTeacherRevisionPlans(
            {published.bound.plan.revision.request_id: published.bound.reference},
            c.source.data.store,
        )
        proof = recorded_teacher_review(
            plans,
            c.original.preparation.policy,
            evidence=c.source.data.store,
            controls=c.source.controls,
            context_authority=c.context,
            counts=c.count_review,
        )
        return c.source.data.journal(teacher_review=proof)

    attempts = UnitAttemptLifecycle(source)
    deps = construction_control_dependencies(
        c.deps.journal,
        c.source.controls,
        readiness=ConstructionReadiness(
            source.runs, source.deps.claims, c.deps.plans, c.source.data.authority
        ),
    )
    deps = replace(
        deps,
        evidence=c.source.data.store,
        attempts=attempts,
        teacher_assembly=c.deps,
        teacher_factory=teacher,
        teacher_journal=journal,
    )
    return ControlCase(c, source, deps, attempts, publications)
