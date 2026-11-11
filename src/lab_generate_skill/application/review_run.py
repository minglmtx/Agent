"""Independent same-release selected construction review; never executes a task.

No website, model, writer, reconstruction, export or training dependencies. The
explicit authority and full recorded-history verifier are mandatory. This first
version does not implement cross-release rejudgment or formal training admission.
"""

from dataclasses import dataclass
from typing import Literal
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    select_target,
)
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.review import ReviewPlan, ReviewReceipt, ReviewFinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.review import ConstructionHistoryVerifier, ReviewAuthority
from .task_teacher_review import TaskTeacherReviewDeps
from .teacher_actor_reads import canonical
from .construction_review_tasks import review_construction_task
from .review_controls import ReviewControl


@dataclass(frozen=True)
class ReviewEvaluator:
    attempt_id: str
    evaluator: Evaluator


@dataclass(frozen=True)
class ReviewDeps:
    evidence: EvidenceReader
    plans: RunPlans
    history: ConstructionHistoryVerifier
    tasks: TaskTeacherReviewDeps
    contexts: ContextRecords
    evaluators: tuple[ReviewEvaluator, ...]
    authority: ReviewAuthority
    controls: OperationControls

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tasks, TaskTeacherReviewDeps)
            or self.tasks.original.evidence is not self.evidence
        ):
            raise ValueError(
                "Same readonly CAS and complete original task/native reviewers required"
            )
        if (
            type(self.evaluators) is not tuple
            or any(
                not isinstance(e, ReviewEvaluator)
                or not e.attempt_id
                or not callable(getattr(e.evaluator, "evaluate", None))
                or not callable(getattr(e.evaluator, "requirements", None))
                for e in self.evaluators
            )
            or len({e.attempt_id for e in self.evaluators}) != len(self.evaluators)
        ):
            raise ValueError("Explicit unique original evaluator bindings required")
        if any(
            not callable(getattr(port, method, None))
            for port, method in (
                (self.evidence, "read"),
                (self.plans, "load"),
                (self.history, "verify"),
                (self.contexts, "load_equivalence"),
                (self.authority, "verify"),
                (self.controls, "bind"),
                (self.history, "verify_current"),
            )
        ):
            raise ValueError(
                "Original readonly proof/runtime dependencies required; no default allow"
            )


class ReviewUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: ReviewPlan,
        phase: str,
        primary: BaseException,
        completed: tuple[ReviewFinding, ...],
    ) -> None:
        self.plan, self.phase, self.primary, self.completed = (
            plan,
            phase,
            primary,
            completed,
        )
        super().__init__(
            "Construction review unconfirmed; keep original facts, never rerun requests"
        )


def review_run(plan: ReviewPlan, deps: ReviewDeps) -> ReviewReceipt:
    plan = ReviewPlan.model_validate(plan)
    findings: list[ReviewFinding] = []
    phase = "sealed_construction"
    try:
        control = deps.controls.bind(plan.operation)
        control.checkpoint()
        progress = canonical(
            plan.sealed_evidence_ref,
            "construction-progress/1",
            ConstructionProgress,
            deps.evidence,
            control,
            8 * 1024**2,
        )
        view = progress.project()
        if (
            progress.plan.run != plan.run
            or view.next_action.kind != "complete"
            or view.selection != plan.selection
            or len(view.attempts) != len(plan.tasks)
            or len(view.candidates) != len(plan.tasks)
        ):
            raise EvidenceIntegrityError(
                "Review requires exact original complete construction and selected branch"
            )
        expected = select_target(view.attempts)
        if expected != view.selection:
            raise EvidenceIntegrityError(
                "Original minimum-interaction stable target selection differs"
            )
        chosen = next(
            (
                r
                for r in view.attempts
                if r.intent.binding.attempt_id == plan.selection.attempt_id
            ),
            None,
        )
        if (
            chosen.evaluation_ref if chosen is not None else None
        ) != plan.selected_evaluation_ref:
            raise EvidenceIntegrityError(
                "Review changed explicit selected original evaluation"
            )
        original = deps.plans.load(plan.run, plan.operation)
        frozen = progress.plan
        if (
            ConstructionPlan.from_run_plan(
                original,
                plan.run,
                frozen.task.identity.task_id,
                claim_ref=frozen.claim_ref,
                public_context_ref=frozen.public_context_ref,
                context_receipt_ref=frozen.context_receipt_ref,
                retrieval_ref=frozen.retrieval_ref,
                retrieval_scope=frozen.retrieval_scope,
                actor_context_configuration_ref=frozen.actor_context_configuration_ref,
            )
            != frozen
        ):
            raise EvidenceIntegrityError("Review changed original frozen RunPlan")
        by_id = {e.attempt_id: e.evaluator for e in deps.evaluators}
        if set(by_id) != {r.intent.binding.attempt_id for r in view.attempts}:
            raise EvidenceIntegrityError(
                "Every original attempt requires its explicit same-release evaluator"
            )
        phase = "review_runtime"
        deps.authority.verify(plan, original, plan.operation, control)
        phase = "original_complete_history"
        deps.history.verify(progress, plan, control)
        selected_skill_ref: EvidenceRef | None = None
        phase = "original_task_native_judgment_close_reset"
        for item, result in zip(plan.tasks, view.attempts, strict=True):
            leaf = ReviewControl(control, deps.controls.bind(item.operation))
            finding, task = review_construction_task(
                item,
                result,
                frozen,
                deps.tasks,
                deps.contexts,
                by_id[result.intent.binding.attempt_id],
                leaf,
            )
            findings.append(finding)
            if chosen == result:
                selected_skill_ref = task.skill_ref
            control.checkpoint()
        status: Literal["verified", "inconsistent", "insufficient_evidence"] = (
            "insufficient_evidence"
            if any(f.reproduced.status == "unknown" for f in findings)
            else (
                "verified"
                if all(f.matches_recorded for f in findings)
                else "inconsistent"
            )
        )
        if status != "verified":
            selected_skill_ref = None
        phase = "final_runtime_and_immutable_source"
        deps.authority.verify(plan, original, plan.operation, control)
        deps.history.verify_current(progress, plan, control)
        if (
            canonical(
                plan.sealed_evidence_ref,
                "construction-progress/1",
                ConstructionProgress,
                deps.evidence,
                control,
                8 * 1024**2,
            )
            != progress
        ):
            raise EvidenceIntegrityError("Sealed construction changed during review")
        return ReviewReceipt(
            plan=plan,
            findings=tuple(findings),
            status=status,
            selected_skill_ref=selected_skill_ref,
        )
    except BaseException as error:
        raise ReviewUnconfirmed(plan, phase, error, tuple(findings)) from error
