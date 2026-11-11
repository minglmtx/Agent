"""Construction-owned pending/full-plan proof behind shared phase source ports."""

import hashlib
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.construction_task_execution import TaskExecutionAuthority
from lab_generate_skill.ports.lifecycle import OperationControl


class ConstructionTaskPhaseSources:
    def __init__(self, construction: ConstructionJournal) -> None:
        if construction is None:
            raise ValueError("Original construction source mandatory")
        self.construction = construction

    def original(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ConstructionProgress:
        control.checkpoint()
        if plan.intent.source_kind != "construction":
            raise OwnershipConflict(
                "Construction phase source requires construction intent"
            )
        progress = ConstructionProgress.model_validate(
            self.construction.read(operation)
        )
        if (
            progress.plan.run != plan.intent.binding.run
            or progress.project().pending_attempt != plan.intent
        ):
            raise OwnershipConflict("Phase lost original pending construction source")
        return progress

    def view(
        self, plan: TaskExecutionPlan, progress: ConstructionProgress
    ) -> TaskPhaseSourceState:
        return TaskPhaseSourceState(
            intent=plan.intent,
            task=progress.plan.task,
            public_context_ref=progress.plan.public_context_ref,
            context_receipt_ref=progress.plan.context_receipt_ref,
            source_sha256=hashlib.sha256(
                progress.model_dump_json().encode()
            ).hexdigest(),
        )

    def read(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskPhaseSourceState:
        return self.view(plan, self.original(plan, operation, control))

    def verify_run(
        self,
        plan: TaskExecutionPlan,
        state: TaskPhaseSourceState,
        run: RunPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        progress = self.original(plan, operation, control)
        if self.view(plan, progress) != state:
            raise RevisionConflict("Original construction source changed")
        p = progress.plan
        expected = ConstructionPlan.from_run_plan(
            run,
            p.run,
            p.task.identity.task_id,
            claim_ref=p.claim_ref,
            public_context_ref=p.public_context_ref,
            context_receipt_ref=p.context_receipt_ref,
            retrieval_ref=p.retrieval_ref,
            retrieval_scope=p.retrieval_scope,
            actor_context_configuration_ref=p.actor_context_configuration_ref,
        )
        if expected != p:
            raise OwnershipConflict("Phase changed full original construction plan")


class ConstructionTaskPhaseResources:
    def __init__(
        self, sources: ConstructionTaskPhaseSources, authority: TaskExecutionAuthority
    ) -> None:
        if sources is None or authority is None:
            raise ValueError("Original source/resource authority required")
        self.sources, self.authority = sources, authority

    def verify(
        self,
        plan: TaskExecutionPlan,
        state: TaskPhaseSourceState,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        read: OperationContext,
        control: OperationControl,
    ) -> None:
        progress = self.sources.original(plan, read, control)
        if self.sources.view(plan, progress) != state:
            raise RevisionConflict(
                "Construction phase source changed before resource check"
            )
        self.authority.verify(plan, progress, snapshot, reset, control)


from lab_generate_skill.ports.construction import ConstructionSourceProof


class ConstructionTaskOriginSource:
    """Preserve selective full construction verification at the Map origin seam."""

    def __init__(self, source: ConstructionSourceProof) -> None:
        if source is None:
            raise ValueError("Original complete construction source proof mandatory")
        self.source = source

    def verify_source(self, operation: OperationContext) -> TaskPhaseSourceState:
        progress = ConstructionProgress.model_validate(
            self.source.verify_source(operation)
        )
        intent = progress.project().pending_attempt
        if intent is None:
            raise OwnershipConflict(
                "Frozen origin requires original pending task intent"
            )
        return TaskPhaseSourceState(
            intent=intent,
            task=progress.plan.task,
            public_context_ref=progress.plan.public_context_ref,
            context_receipt_ref=progress.plan.context_receipt_ref,
            source_sha256=hashlib.sha256(
                progress.model_dump_json().encode()
            ).hexdigest(),
        )
