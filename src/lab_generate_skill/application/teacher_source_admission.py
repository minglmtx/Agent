"""Bind complete Teacher sources to original live/recorded construction facts.

This implements source ownership, not native leaf/feedback/provider permission.
Compose it with NativeTeacherSourceAuthority and the original leaf authority.
No writes, recovery, resource actions, reservation or dispatch occur here.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.teacher_source import TeacherSourceBindings
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.construction import (
    ConstructionJournal,
    ConstructionAuthority,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from .teacher_source_inputs import check_source_schedule


@dataclass(frozen=True)
class TeacherConstructionSourceDeps:
    construction: ConstructionJournal
    runs: RunJournal
    claims: SourceClaims
    contexts: ContextRecords
    plans: RunPlans
    original: ConstructionAuthority


class ConstructionTeacherSourceAuthority:
    def __init__(
        self,
        run: RunBinding,
        deps: TeacherConstructionSourceDeps,
        recorded_operation: OperationContext,
    ) -> None:
        if any(
            value is None
            for value in (
                deps.construction,
                deps.runs,
                deps.claims,
                deps.contexts,
                deps.plans,
                deps.original,
            )
        ):
            raise ValueError(
                "Original construction/run/claim/context authority required"
            )
        self.run = RunBinding.model_validate(run)
        self.deps = deps
        self.recorded_operation = OperationContext.model_validate(recorded_operation)

    def _verify(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        operation: OperationContext,
        *,
        preparing: bool,
        control: OperationControl,
    ) -> None:
        progress = ConstructionProgress.model_validate(progress)
        bindings = TeacherSourceBindings.model_validate(bindings)
        op = OperationContext.model_validate(operation)
        original = bindings.operation
        control.checkpoint()
        if progress.plan.run != self.run or (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
        ) != (self.run.owner.run_id, self.run.owner.owner_id, None, None, None):
            raise OwnershipConflict(
                "Teacher source differs from original run/read scope"
            )
        if op != original and not (
            not preparing
            and op.mode == "cleanup"
            and op.parent_operation_id == original.operation_id
        ):
            raise OwnershipConflict(
                "Teacher source requires original command or parent cleanup"
            )
        check_source_schedule(progress, bindings)
        # Original caller/writer/semantic permission remains mandatory; no default allow.
        self.deps.original.verify_plan(progress.plan, op)
        control.checkpoint()
        current = ConstructionProgress.model_validate(self.deps.construction.read(op))
        snapshot = RunSnapshot.model_validate(self.deps.runs.read(op))
        if snapshot.binding != self.run or current.plan != progress.plan:
            raise OwnershipConflict(
                "Teacher source journals differ from original run/plan"
            )
        if current.events[: len(progress.events)] != progress.events:
            raise OwnershipConflict(
                "Teacher source is not the original immutable history prefix"
            )
        run, attempts = snapshot.project()
        if preparing:
            if (
                current != progress
                or run.stage != "running"
                or run.stop_reason is not None
            ):
                raise InvalidTransition(
                    "New Teacher source requires current ready history and running run"
                )
            used = {e.operation.operation_id for e in current.events}
            used.update(e.event.operation.operation_id for e in snapshot.entries)
            if original.operation_id in used:
                raise OwnershipConflict(
                    "Teacher source cannot reuse a recorded operation"
                )
        # Registered construction results must refer to the same original sealed attempts.
        by_id = {a.binding.attempt_id: a for a in attempts}
        for result in progress.project().attempts:
            recorded = by_id.get(result.intent.binding.attempt_id)
            if (
                recorded is None
                or recorded.binding != result.intent.binding
                or recorded.stage != "sealed"
            ):
                raise OwnershipConflict(
                    "Teacher source lacks the original sealed attempt history"
                )
        loaded = self.deps.plans.load(self.run, op)
        expected = ConstructionPlan.from_run_plan(
            loaded,
            self.run,
            progress.plan.task.identity.task_id,
            claim_ref=progress.plan.claim_ref,
            public_context_ref=progress.plan.public_context_ref,
            context_receipt_ref=progress.plan.context_receipt_ref,
            retrieval_ref=progress.plan.retrieval_ref,
            retrieval_scope=progress.plan.retrieval_scope,
            actor_context_configuration_ref=progress.plan.actor_context_configuration_ref,
        )
        if expected != progress.plan:
            raise OwnershipConflict(
                "Teacher source changed complete original RunPlan membership"
            )
        claim = self.deps.claims.require_source(
            progress.plan.claim_ref, self.run, progress.plan.task, op
        )
        check_source_claim(claim, progress.plan.claim_ref, self.run, progress.plan.task)
        context = self.deps.contexts.load_context(progress.plan.context_receipt_ref, op)
        if (
            context.public_context_ref != progress.plan.public_context_ref
            or context.scope.task != progress.plan.task.identity
            or context.spec_ref != progress.plan.task.baseline_ref
            or (context.scope.owner.run_id, context.scope.owner.owner_id)
            != (self.run.owner.run_id, self.run.owner.owner_id)
        ):
            raise OwnershipConflict("Teacher source changed original qualified context")
        control.checkpoint()
        self.deps.original.verify_plan(progress.plan, op)
        if (
            ConstructionProgress.model_validate(self.deps.construction.read(op))
            != current
            or RunSnapshot.model_validate(self.deps.runs.read(op)) != snapshot
        ):
            raise RevisionConflict(
                "Original journals changed during Teacher source admission"
            )
        control.checkpoint()

    def verify_prepare(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        bindings = TeacherSourceBindings.model_validate(bindings)
        self._verify(
            progress, bindings, bindings.operation, preparing=True, control=control
        )

    def verify_recorded(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        self._verify(
            progress,
            bindings,
            self.recorded_operation,
            preparing=False,
            control=control,
        )
