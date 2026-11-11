"""Read original ExecutionWorkload/policy/context/claim, with no effects or grant."""

import os
import threading
from contextlib import contextmanager
from collections.abc import Iterator
from lab_generate_skill.adapters.operation_progress import operation_stage
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskSource,
    ExecutionTaskInputs,
    ExecutionSourceFacts,
    ClaimedExecutionSourceFacts,
    check_execution_source_facts,
    execution_context_owner,
)
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.execution import RunBinding, AttemptBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.execution_task import (
    ExecutionTaskSourceChecks,
    ExecutionTaskSourceCurrentChecks,
)
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.claims import SourceClaims, SourceClaimBodyChecks
from lab_generate_skill.ports.source_stage_validation import StageValidationClaimBinding
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_reads import StateReads


class OriginalExecutionTaskSource:
    def __init__(
        self,
        plans: RunPlans,
        claims: SourceClaims,
        contexts: ContextRecords,
        bindings: TaskBindings,
        evidence: EvidenceReader,
        *,
        source_checks: ExecutionTaskSourceChecks | None = None,
    ) -> None:
        if any(x is None for x in (plans, claims, contexts, bindings, evidence)):
            raise ValueError("Original plans/claim/context/task readers mandatory")
        self.plans, self.claims, self.contexts, self.bindings = (
            plans,
            claims,
            contexts,
            bindings,
        )
        self.reads = StateReads(evidence)
        self.source_checks = source_checks
        self._task_plan: TaskExecutionPlan | None = None
        self._task_facts: ExecutionSourceFacts | None = None
        self._task_checks: ExecutionTaskSourceChecks | None = None
        self._task_owner: tuple[int, int] | None = None
        self._task_used = False

    @contextmanager
    def task_scope(self, plan: TaskExecutionPlan) -> Iterator[None]:
        """Pass this task's original immutable source to its later live gates.

        The fixed current-owner/storage port and the claim ledger are checked
        on every load. Legacy readers still perform full graph reads. Nothing
        survives the existing resource scope, including failed finalization.
        """
        plan = TaskExecutionPlan.model_validate(plan)
        if self._task_used or self._task_plan is not None:
            raise OwnershipConflict("Original source task scope is one-shot")
        self._task_used = True
        self._task_plan, self._task_checks = plan, self.source_checks
        self._task_owner = os.getpid(), threading.get_ident()
        try:
            yield
        finally:
            self._task_facts = None
            self._task_plan = None
            self._task_checks = None
            self._task_owner = None

    def load(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ExecutionSourceFacts:
        plan = TaskExecutionPlan.model_validate(plan)
        if plan.intent.source_kind != "execution" or plan.source_ref is None:
            raise OwnershipConflict("Actual execution-only plan/source required")
        op = OperationContext.model_validate(operation)
        self._scope(plan.intent.binding.run, op)
        if self._task_plan is not None:
            if (
                plan != self._task_plan
                or self._task_checks is not self.source_checks
                or self._task_owner != (os.getpid(), threading.get_ident())
            ):
                raise OwnershipConflict(
                    "Source bodies left original task/reader/thread"
                )
            if self._task_facts is not None:
                self.recheck(plan, self._task_facts, op, control)
                return self._task_facts
        if self.source_checks is None:
            source = self.reads.parse(
                plan.source_ref,
                plan.source_ref.content_schema,
                ExecutionTaskSource,
                control,
            )
            if source.intent != plan.intent or source.run != plan.intent.binding.run:
                raise OwnershipConflict(
                    "Execution manifest changed original intent/run"
                )
            facts = self.verify_source(source, operation, control)
        else:
            # One installed proof for this read; an active owned task may pass
            # its immutable bodies onward, with fresh storage/claim gates.
            control.checkpoint()
            with operation_stage("source.immutable-proof"):
                facts = self.source_checks.load_source(plan, op, control)
            self._claim(facts, op, control)
        if (
            facts.source.intent != plan.intent
            or facts.source.run != plan.intent.binding.run
            or facts.inputs.task_binding_ref != plan.evaluation.task_contract_ref
            or facts.inputs.skill_ref != plan.skill_ref
        ):
            raise OwnershipConflict(
                "Execution source changed original task plan/evaluation/skill"
            )
        if self._task_plan is not None and isinstance(
            self.source_checks, ExecutionTaskSourceCurrentChecks
        ):
            self._task_facts = facts
        return facts

    def recheck(
        self,
        plan: TaskExecutionPlan,
        facts: ExecutionSourceFacts,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Verify passed bodies; claim and current storage are never cached.

        The admission consumer rechecks current source rights and RunJournal
        after the resource check. This gate does not retain any facts.
        """
        plan = TaskExecutionPlan.model_validate(plan)
        if not isinstance(facts, ExecutionSourceFacts):
            raise TypeError("Original immutable ExecutionSourceFacts required")
        op = OperationContext.model_validate(operation)
        self._scope(plan.intent.binding.run, op)
        control.checkpoint()
        if (
            plan.intent.source_kind != "execution"
            or plan.source_ref is None
            or facts.source.intent != plan.intent
            or facts.source.run != plan.intent.binding.run
            or facts.inputs.task_binding_ref != plan.evaluation.task_contract_ref
            or facts.inputs.skill_ref != plan.skill_ref
        ):
            raise OwnershipConflict("Source handoff changed original plan/facts")
        if isinstance(self.source_checks, ExecutionTaskSourceCurrentChecks):
            self.source_checks.verify_current(plan, facts, op, control)
            self._claim(facts, op, control)
        elif self.load(plan, op, control) != facts:
            raise RevisionConflict("Original source changed during admission")
        control.checkpoint()

    def verify_source(
        self,
        source: ExecutionTaskSource,
        operation: OperationContext,
        control: OperationControl,
    ) -> ExecutionSourceFacts:
        source = ExecutionTaskSource.model_validate(source)
        op = OperationContext.model_validate(operation)
        self._scope(source.run, op)
        self._claim_origin(source.frozen_origin)
        parent_source = None
        if source.frozen_origin is not None:
            parent_source = self.reads.parse(
                source.frozen_origin.parent_source_ref,
                "execution-task-source/1",
                ExecutionTaskSource,
                control,
            )
        execution_context_owner(source, parent_source)
        run = self.plans.load(source.run, op)
        workload = run.workload
        if (
            not isinstance(workload, ExecutionWorkload)
            or run.purpose != "engineering"
            or run.split != "train"
            or len(run.tasks) != 1
            or run.tasks != (source.task,)
            or len(run.models) != 1
            or run.models[0].role != "actor"
            or run.models[0].paid
        ):
            raise OwnershipConflict(
                "Current single engineering scope is train/actor-only/unpaid"
            )
        if (
            workload.execution_policy_ref != source.intent.execution_policy_ref
            or workload.task_inputs_ref != source.intent.execution_inputs_ref
        ):
            raise OwnershipConflict("Execution policy/inputs changed original RunPlan")
        inputs = self.reads.parse(
            workload.task_inputs_ref,
            "execution-task-inputs/1",
            ExecutionTaskInputs,
            control,
        )
        policy = self.reads.parse(
            workload.execution_policy_ref,
            "engineering-execution-policy/3",
            EngineeringActorPolicy,
            control,
        )
        binding = self.bindings.load(inputs.task_binding_ref, op)
        public = self.reads.parse(
            binding.public_task_ref,
            "public-task/1",
            PublicTask,
            control,
            visibility="public",
        )
        context = self.contexts.load_context(source.source_context_receipt_ref, op)
        facts = check_execution_source_facts(
            source,
            inputs,
            run,
            policy,
            binding,
            public,
            context,
            skill=self.reads.read(inputs.skill_ref, control),
            parent_source=parent_source,
        )
        self._claim(facts, op, control)
        return facts

    def _claim(
        self,
        facts: ExecutionSourceFacts,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        source = facts.source
        self._claim_origin(source.frozen_origin)
        with operation_stage("source.current-claim"):
            if isinstance(facts, ClaimedExecutionSourceFacts) and isinstance(
                self.claims, SourceClaimBodyChecks
            ):
                if facts.claim.reference != source.intent.binding.claim_ref:
                    raise OwnershipConflict(
                        "Source body changed original claim reference"
                    )
                claim = self.claims.require_source_verified(
                    facts.claim, source.run, source.task, op
                )
            else:
                claim = self.claims.require_source(
                    source.intent.binding.claim_ref, source.run, source.task, op
                )
        check_source_claim(
            claim, source.intent.binding.claim_ref, source.run, source.task
        )
        control.checkpoint()

    def _claim_origin(self, origin: FrozenExecutionOrigin | None) -> None:
        staged = isinstance(self.claims, StageValidationClaimBinding)
        if (origin is not None) != staged:
            raise OwnershipConflict(
                "Frozen-source mode must match the actual claim ledger"
            )
        if origin is not None:
            assert isinstance(self.claims, StageValidationClaimBinding)
            if self.claims.validation != origin.validation:
                raise OwnershipConflict(
                    "Frozen source changed its durable validation descriptor"
                )

    def bind_source(
        self,
        run: RunBinding,
        claim_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
        *,
        frozen_origin: FrozenExecutionOrigin | None = None,
    ) -> ExecutionSourceFacts:
        """Build from existing frozen inputs/owned claim, without any fake task plan.

        This performs read-only semantic validation. It never creates a claim,
        changes its scope/owner, generates an attempt ID or grants execution.
        """
        run = RunBinding.model_validate(run)
        operation = OperationContext.model_validate(operation)
        self._scope(run, operation)
        self._claim_origin(frozen_origin)
        control.checkpoint()
        original = self.plans.load(run, operation)
        workload = original.workload
        if not isinstance(workload, ExecutionWorkload) or len(original.tasks) != 1:
            raise OwnershipConflict(
                "Single source publication requires original one-task execution workload"
            )
        inputs = self.reads.parse(
            workload.task_inputs_ref,
            "execution-task-inputs/1",
            ExecutionTaskInputs,
            control,
        )
        policy = self.reads.parse(
            workload.execution_policy_ref,
            "engineering-execution-policy/3",
            EngineeringActorPolicy,
            control,
        )
        context = self.contexts.load_context(
            inputs.source_context_receipt_ref, operation
        )
        intent = TaskAttemptIntent(
            schema_version="execution-task-intent/1",
            binding=AttemptBinding(
                run=run,
                task=original.tasks[0].identity,
                attempt_id=inputs.attempt_id,
                claim_ref=claim_ref,
            ),
            skill_digest=policy.skill.content_digest,
            public_context_ref=context.public_context_ref,
            execution_policy_ref=workload.execution_policy_ref,
            execution_inputs_ref=workload.task_inputs_ref,
        )
        if frozen_origin is None:
            source = ExecutionTaskSource(
                run=run,
                task=original.tasks[0],
                intent=intent,
                source_context_receipt_ref=inputs.source_context_receipt_ref,
            )
        else:
            source = ExecutionTaskSource(
                schema_version="execution-task-source/2",
                run=run,
                task=original.tasks[0],
                intent=intent,
                source_context_receipt_ref=inputs.source_context_receipt_ref,
                frozen_origin=frozen_origin,
            )
        return self.verify_source(source, operation, control)

    @staticmethod
    def _scope(run: RunBinding, operation: OperationContext) -> None:
        owner = run.owner
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
        ) != (owner.run_id, owner.owner_id, None, None, None):
            raise OwnershipConflict(
                "Source reads require original independent run scope"
            )
