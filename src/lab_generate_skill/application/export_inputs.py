"""Rebuild the original public Generator input and selected evidence for export."""

from collections.abc import Callable
from dataclasses import replace
from lab_generate_skill.domain.review import ReviewPlan, ReviewReceipt
from lab_generate_skill.domain.export import (
    ExportPlan,
    ExportScope,
    ExportSource,
    TrainingTargetQualification,
)
from lab_generate_skill.domain.export_material import ExportMaterial
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.construction import CallPlanned
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.generator_admission import (
    ConstructionGenerationRecords,
    GeneratorRequestProjection,
)
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from .review_run import ReviewDeps, review_run
from .review_controls import ReviewControl
from .teacher_actor_reads import canonical


def same_review_source(a: ReviewPlan, b: ReviewPlan) -> bool:
    return (
        a.run,
        a.original_run_plan_ref,
        a.sealed_evidence_ref,
        a.original_execution_release,
        a.judgment_release,
        a.selection,
        a.selected_evaluation_ref,
        tuple(t.published for t in a.tasks),
        tuple(t.published for t in a.teachers),
    ) == (
        b.run,
        b.original_run_plan_ref,
        b.sealed_evidence_ref,
        b.original_execution_release,
        b.judgment_release,
        b.selection,
        b.selected_evaluation_ref,
        tuple(t.published for t in b.tasks),
        tuple(t.published for t in b.teachers),
    )


class _ReadControls:
    def __init__(
        self, original: OperationControls, enclosing: OperationControl
    ) -> None:
        self.original, self.enclosing = original, enclosing

    def bind(self, op: object) -> OperationControl:
        from lab_generate_skill.domain.lifecycle import OperationContext

        return ReviewControl(
            self.enclosing, self.original.bind(OperationContext.model_validate(op))
        )


class RecordedExportInputs:
    def __init__(
        self,
        evidence: EvidenceReader,
        reviews: Callable[[ReviewPlan], ReviewDeps],
        generation: ConstructionGenerationRecords,
        observations: ObservationLoader,
        project: GeneratorRequestProjection,
    ) -> None:
        if (
            evidence is None
            or not callable(reviews)
            or not callable(project)
            or generation is None
            or observations is None
        ):
            raise ValueError(
                "Original source review/public Generator input dependencies required"
            )
        (
            self.evidence,
            self.reviews,
            self.generation,
            self.observations,
            self.project,
        ) = (evidence, reviews, generation, observations, project)

    def load(
        self,
        source: ExportSource,
        plan: ExportPlan,
        scope: ExportScope,
        split: SplitManifest,
        control: OperationControl,
    ) -> ExportMaterial:
        recorded = canonical(
            source.review_ref,
            "construction-review-receipt/1",
            ReviewReceipt,
            self.evidence,
            control,
            8 * 1024**2,
        )
        if not same_review_source(recorded.plan, source.review_read):
            raise EvidenceIntegrityError(
                "Export changed the explicitly selected original review branch"
            )
        review_deps = self.reviews(source.review_read)
        if review_deps.evidence is not self.evidence:
            raise EvidenceIntegrityError("Export source reader changed original CAS")
        guarded = replace(
            review_deps, controls=_ReadControls(review_deps.controls, control)
        )
        current = review_run(source.review_read, guarded)
        if (recorded.status, recorded.findings, recorded.selected_skill_ref) != (
            current.status,
            current.findings,
            current.selected_skill_ref,
        ):
            raise EvidenceIntegrityError(
                "Export review no longer reproduces original evidence; select a new explicit review"
            )
        progress = canonical(
            recorded.plan.sealed_evidence_ref,
            "construction-progress/1",
            ConstructionProgress,
            self.evidence,
            control,
            8 * 1024**2,
        )
        if (
            progress.plan.run not in scope.allowed_runs
            or progress.plan.task.identity not in scope.allowed_tasks
        ):
            raise EvidenceIntegrityError(
                "Original source is outside explicit export scope"
            )
        run = review_deps.plans.load(progress.plan.run, source.review_read.operation)
        if (
            run.split_manifest_ref != plan.split_ref
            or progress.plan.retrieval_scope.split_ref != plan.split_ref
        ):
            raise EvidenceIntegrityError("Export changed exact original split manifest")
        member = split.member(progress.plan.task.identity)
        qualification = canonical(
            source.qualification_ref,
            "training-target-qualification/1",
            TrainingTargetQualification,
            self.evidence,
            control,
            1024**2,
        )
        if (
            qualification.run,
            qualification.task,
            qualification.scope_ref,
            qualification.review_ref,
            qualification.sealed_evidence_ref,
            qualification.selected_evaluation_ref,
            qualification.target_skill_ref,
            qualification.retrieval_ref,
        ) != (
            progress.plan.run,
            progress.plan.task.identity,
            plan.scope_ref,
            source.review_ref,
            recorded.plan.sealed_evidence_ref,
            recorded.plan.selected_evaluation_ref,
            recorded.selected_skill_ref,
            progress.plan.retrieval_ref,
        ):
            raise EvidenceIntegrityError(
                "Qualification changed actual source/review/input/selection"
            )
        first = next(
            (
                e.call
                for e in progress.events
                if isinstance(e, CallPlanned) and e.call.role == "generator"
            ),
            None,
        )
        if first is None or (first.candidate_slot, first.resample_index) != (0, 0):
            raise EvidenceIntegrityError(
                "Original first public Generator call required"
            )
        original = self.generation.load(
            progress.plan, first, source.review_read.operation, control
        )
        observed = self.observations.load(
            original.context.initial_observation_ref, source.review_read.operation
        )
        prompt = self.project(original, observed)
        skill = None
        task = None
        if recorded.selected_skill_ref is not None:
            skill = canonical(
                recorded.selected_skill_ref,
                "compact-skill/1",
                CompactSkill,
                self.evidence,
                control,
                public=True,
            )
            selected = next(
                r
                for r in progress.project().attempts
                if r.intent.binding.attempt_id == recorded.plan.selection.attempt_id
            )
            envelope = canonical(
                selected.attempt_ref,
                "attempt-result/1",
                TaskAttemptResult,
                self.evidence,
                control,
            )
            executed = canonical(
                envelope.execution_ref,
                "executed-task-receipt/1",
                ExecutedTaskReceipt,
                self.evidence,
                control,
            )
            task = canonical(
                executed.plan_ref,
                "task-execution-plan/1",
                TaskExecutionPlan,
                self.evidence,
                control,
            )
            if (
                task.skill_ref != recorded.selected_skill_ref
                or skill.content_digest != selected.intent.skill_digest
            ):
                raise EvidenceIntegrityError(
                    "Export target differs from the independently selected actual skill"
                )
        control.checkpoint()
        return ExportMaterial(
            recorded,
            current,
            progress,
            run,
            qualification,
            member,
            first.input_ref,
            original,
            prompt,
            skill,
            task,
        )
