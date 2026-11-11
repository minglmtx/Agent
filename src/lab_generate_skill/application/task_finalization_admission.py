"""Current cleanup journals/claim/full-plan join plus mandatory original grant.

Cancellation can stop new work while original owned cleanup remains possible.
No metadata check here establishes physical closure, non-start or native rights.
"""

import hashlib
from lab_generate_skill.domain.claims import check_source_claim, SourceClaimRecord
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.ports.claims import SourceClaims, AttemptClaimBodyChecks
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseRunRead,
    TaskPhaseRunReads,
    TaskPhaseClaimRead,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.task_finalization import (
    TaskFinalizationAuthority as TaskFinalizationSourceAuthority,
    TaskFinalizationDeclarationInputs,
)
from .context_evidence import read_bytes
from .task_cleanup_operations import require_original_cleanup_operation


class TaskFinalizationAuthority:
    def __init__(
        self,
        declaration_ref: EvidenceRef,
        sources: TaskPhaseSources,
        runs: RunJournal,
        claims: SourceClaims,
        plans: RunPlans,
        source: TaskFinalizationSourceAuthority,
        evidence: EvidenceStore,
    ) -> None:
        if any(x is None for x in (sources, runs, claims, plans, source, evidence)):
            raise ValueError(
                "Original cleanup journals/claim/plan/source authorities mandatory"
            )
        if (
            declaration_ref.content_schema,
            declaration_ref.visibility,
            declaration_ref.media_type,
        ) != ("task-finalization-plan/1", "private", "application/json"):
            raise ValueError(
                "Original frozen private finalization declaration required"
            )
        self.declaration_ref, self.sources, self.runs = (
            declaration_ref,
            sources,
            runs,
        )
        self.claims, self.plans, self.source, self.evidence = (
            claims,
            plans,
            source,
            evidence,
        )

    def read_finalization_declaration(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> bytes:
        if isinstance(self.source, TaskFinalizationDeclarationInputs):
            return self.source.read_finalization_declaration(
                plan, declaration, reference, operation, control
            )
        return read_bytes(self.evidence, reference, 2 * 1024**2, control)

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        plan = TaskExecutionPlan.model_validate(plan)
        declaration = TaskFinalizationPlan.model_validate(declaration)
        operation = OperationContext.model_validate(operation)
        if (
            plan.declaration_ref.content_schema,
            plan.declaration_ref.visibility,
            plan.declaration_ref.media_type,
        ) != ("site-task-preparation-plan/2", "private", "application/json"):
            raise OwnershipConflict(
                "Cleanup requires original typed private preparation declaration"
            )
        if not isinstance(references, tuple) or any(
            not isinstance(r, EvidenceRef) for r in references
        ):
            raise TypeError(
                "Original complete recovery references must be a typed tuple"
            )
        if operation.mode != "cleanup" or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
        ) != (
            plan.operation.run_id,
            plan.operation.owner_id,
            plan.operation.attempt_id,
        ):
            raise OwnershipConflict(
                "No new work or changed original attempt in cleanup"
            )
        if control.checkpoint() > plan.cleanup_seconds:
            raise OwnershipConflict("Cleanup widened original task budget")
        # The old execute read operation may be expired/cancelled. These are
        # bounded read-only children of this actual cleanup, not new dispatches.
        key = hashlib.sha256(operation.model_dump_json().encode()).hexdigest()
        read = operation.model_copy(
            update={
                "operation_id": "task-cleanup-read-" + key,
                "attempt_id": None,
                "allocation_id": None,
                "recovery_ref": None,
                "parent_operation_id": operation.operation_id,
            }
        )
        claim_op = read.model_copy(
            update={
                "operation_id": "task-cleanup-claim-" + key,
                "attempt_id": operation.attempt_id,
            }
        )
        source_read = (
            self.sources.open_run_read(plan, read, control)
            if isinstance(self.sources, TaskPhaseRunReads)
            else None
        )
        try:
            self._verify_current(
                plan,
                declaration,
                references,
                operation,
                read,
                claim_op,
                control,
                source_read,
            )
        finally:
            if source_read is not None:
                source_read.close()

    def _verify_current(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        read: OperationContext,
        claim_op: OperationContext,
        control: OperationControl,
        source_read: TaskPhaseRunRead | None,
    ) -> None:
        progress = (
            source_read.state
            if source_read is not None
            else self.sources.read(plan, read, control)
        )
        snapshot = RunSnapshot.model_validate(self.runs.read(read))
        run, attempts = snapshot.project()
        original = [a for a in attempts if a.binding == plan.intent.binding]
        if (
            snapshot.binding != plan.intent.binding.run
            or progress.intent.binding.run != snapshot.binding
            or progress.intent != plan.intent
            or len(original) != 1
            or run.stage not in ("running", "closing")
            or run.stage == "closing"
            and run.stop_reason is None
            or plan.intent.binding.claim_ref != progress.intent.binding.claim_ref
        ):
            raise OwnershipConflict(
                "Cleanup needs original pending attempt in live/closing run"
            )
        reset = ResetPlan.model_validate_json(
            self.read_finalization_declaration(
                plan, declaration, plan.reset_plan_ref, operation, control
            )
        )
        prepared = SiteTaskPreparationPlan.model_validate_json(
            self.read_finalization_declaration(
                plan, declaration, plan.declaration_ref, operation, control
            )
        )
        binding = TaskBinding.model_validate_json(
            self.read_finalization_declaration(
                plan, declaration, prepared.task_binding_ref, operation, control
            )
        )
        if (
            (reset.scope, prepared.scope) != (declaration.scope, declaration.scope)
            or (
                declaration.scope.owner,
                declaration.scope.task,
                declaration.scope.attempt_id,
            )
            != (
                plan.intent.binding.run.owner,
                plan.intent.binding.task,
                plan.intent.binding.attempt_id,
            )
            or binding != progress.task
            or reset.parent_operation_id != prepared.prepare_operation.operation_id
            or self.read_finalization_declaration(
                plan, declaration, self.declaration_ref, operation, control
            )
            != declaration.model_dump_json().encode()
        ):
            raise OwnershipConflict(
                "Cleanup changed original declaration/task/reset lineage"
            )
        attempt = original[0]
        require_original_cleanup_operation(
            plan, declaration, prepared, reset, attempt, operation
        )
        planned = attempt.events[0]
        if (
            planned.stage != "planned"
            or len(planned.outputs) != 1
            or planned.outputs[0].content_schema != plan.schema_version
            or planned.outputs[0].visibility != "private"
            or planned.outputs[0].media_type != "application/json"
            or self.read_finalization_declaration(
                plan, declaration, planned.outputs[0], operation, control
            )
            != plan.model_dump_json().encode()
        ):
            raise OwnershipConflict(
                "Cleanup changed exact originally planned task bytes"
            )
        loaded = (
            source_read.run
            if source_read is not None
            else self.plans.load(progress.intent.binding.run, read)
        )
        if source_read is None:
            self.sources.verify_run(plan, progress, loaded, read, control)
        elif source_read.recheck(control) != progress:
            raise RevisionConflict(
                "Original cleanup source changed before permission check"
            )
        if plan.cleanup_seconds > loaded.resources.cleanup_timeout_seconds:
            raise OwnershipConflict("Cleanup changed original full plan/budget")
        claim_body = (
            source_read.claim if isinstance(source_read, TaskPhaseClaimRead) else None
        )

        def require_current_claim() -> SourceClaimRecord:
            if claim_body is not None and isinstance(
                self.claims, AttemptClaimBodyChecks
            ):
                return self.claims.require_verified(
                    claim_body, plan.intent.binding, claim_op
                )
            return self.claims.require(
                progress.intent.binding.claim_ref, plan.intent.binding, claim_op
            )

        claim = require_current_claim()
        check_source_claim(
            claim,
            progress.intent.binding.claim_ref,
            progress.intent.binding.run,
            progress.task,
        )
        self.source.verify(plan, declaration, references, operation, control)
        claim2 = require_current_claim()
        check_source_claim(
            claim2,
            progress.intent.binding.claim_ref,
            progress.intent.binding.run,
            progress.task,
        )
        if (
            source_read.recheck(control)
            if source_read is not None
            else self.sources.read(plan, read, control)
        ) != progress or self.runs.read(read) != snapshot:
            raise RevisionConflict("Original cleanup journals changed during admission")
        control.checkpoint()
