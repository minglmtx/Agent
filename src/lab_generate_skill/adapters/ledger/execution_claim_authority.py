"""Original live Slurm owner for an unpaid, actor-only engineering source claim.

Use with the existing FileSourceClaims at a trusted deployment root. No ledger,
runner, takeover, paid/formal permission or string-only owner approval is added.
The context port must be the actual qualified source reader supplied by bootstrap.
Cleanup ownership reads do not reapply permission to start new work.
"""

import os
import threading
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimRecord,
    check_claim_operation,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import PreparedTask, EnvironmentBaseline
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.validation import Identifier
from pydantic import TypeAdapter
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.run_plan import RunPlans


class OriginalExecutionClaimAuthority:
    def __init__(
        self,
        scope_id: str,
        run: RunBinding,
        task: TaskBinding,
        execution: SlurmExecutionIdentity,
        controller: SlurmCgroupMembership,
        *,
        evidence: EvidenceReader,
        plans: RunPlans,
        contexts: ContextRecords,
        controls: OperationControls,
    ) -> None:
        self.scope_id = TypeAdapter(Identifier).validate_python(scope_id, strict=True)
        self.run, self.task = RunBinding.model_validate(
            run
        ), TaskBinding.model_validate(task)
        self.execution = SlurmExecutionIdentity.model_validate(execution)
        self.controller = SlurmCgroupMembership.model_validate(controller)
        if any(v is None for v in (evidence, plans, contexts, controls)):
            raise TypeError(
                "Original qualified source, frozen plans and controls required"
            )
        self.reads, self.plans, self.contexts, self.controls = (
            StateReads(evidence),
            plans,
            contexts,
            controls,
        )
        self._owner = os.getpid(), threading.get_ident()
        if (
            self.run.owner.job_id != self.execution.job_id
            or self.controller.job_id != self.execution.raw_job_id
            or self.controller.uid != self.execution.uid
            or self.task.identity.split != "train"
        ):
            raise OwnershipConflict(
                "Engineering claim changed original Slurm job/task scope"
            )

    def _owner_check(self, operation: OperationContext) -> None:
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        control.checkpoint()
        if (
            self._owner != (os.getpid(), threading.get_ident())
            or (operation.run_id, operation.owner_id)
            != (self.run.owner.run_id, self.run.owner.owner_id)
            or os.getresuid() != (self.execution.uid,) * 3
            or current_process_identity() != self.controller.writer
        ):
            raise OwnershipConflict(
                "Claim caller is not its original live Slurm controller"
            )
        if (
            observe_process_cgroup(
                self.execution, self.controller.writer, control
            ).membership
            != self.controller
        ):
            raise OwnershipConflict("Claim caller left its original Slurm user subtree")
        control.checkpoint()

    def require_caller(self, operation: OperationContext) -> None:
        """Actual original controller only; no claim/plan I/O or new-work grant."""
        self._owner_check(operation)

    def authorize_create(
        self, binding: SourceClaimBinding, plan: RunPlan, op: OperationContext
    ) -> None:
        binding = SourceClaimBinding.model_validate(binding)
        plan = RunPlan.model_validate(plan)
        check_claim_operation(binding, op, creating=True)
        self._owner_check(op)
        control = self.controls.bind(op)
        if (
            (binding.scope_id, binding.run, binding.task)
            != (self.scope_id, self.run, self.task)
            or self.plans.load(self.run, op) != plan
            or plan.purpose != "engineering"
            or plan.split != "train"
            or plan.tasks != (self.task,)
            or not isinstance(plan.workload, ExecutionWorkload)
            or len(plan.models) != 1
            or plan.models[0].role != "actor"
            or plan.models[0].paid
            or plan.budget is not None
            or plan.resources.max_parallel_tasks != 1
        ):
            raise OwnershipConflict(
                "Claim requires exact original unpaid actor-only engineering plan"
            )
        read = self.reads.parse
        inputs = read(
            plan.workload.task_inputs_ref,
            "execution-task-inputs/1",
            ExecutionTaskInputs,
            control,
        )
        policy = read(
            plan.workload.execution_policy_ref,
            "engineering-execution-policy/3",
            EngineeringActorPolicy,
            control,
        )
        source = self.contexts.load_context(inputs.source_context_receipt_ref, op)
        baseline = read(
            source.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
        )
        environment = read(
            baseline.environment_ref,
            "environment-baseline/1",
            EnvironmentBaseline,
            control,
        )
        original_sites = {
            ref
            for check in environment.checks.checks
            for ref in check.evidence
            if ref.content_schema == "site-resource-spec/1"
        }
        if len(original_sites) != 1:
            raise OwnershipConflict(
                "Claim requires the source environment's original physical site"
            )
        site = read(
            next(iter(original_sites)),
            "site-resource-spec/1",
            SiteResourceSpec,
            control,
        )
        if (site.slurm.execution, site.slurm.parent, site.token.owner) != (
            self.execution,
            self.controller,
            self.run.owner,
        ):
            raise OwnershipConflict(
                "Claim cannot retag a closed source to a different job/controller"
            )
        prepared = read(baseline.prepared_ref, "prepared-task/1", PreparedTask, control)
        task = read(inputs.task_binding_ref, "task-binding/1", TaskBinding, control)
        public = read(
            source.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        if (
            source.scope.owner != self.run.owner
            or source.scope.task != self.task.identity
            or source.scope.attempt_id == inputs.attempt_id
            or source.spec_ref != self.task.baseline_ref
            or task != self.task
            or prepared.task_binding_ref != inputs.task_binding_ref
            or prepared.scope != source.scope
            or public.task.identity != self.task.identity
            or public.task.model_dump_json().encode()
            != self.reads.read(self.task.public_task_ref, control)
            or policy.skill.model_dump_json().encode()
            != self.reads.read(inputs.skill_ref, control)
            or policy.max_generations
            != plan.resources.max_actor_generations_per_attempt
            or policy.max_interactions != plan.resources.max_interactions_per_attempt
            or policy.memory != plan.policies.actor_memory
        ):
            raise OwnershipConflict(
                "Claim changed actual qualified source/task/attempt/Actor policy"
            )
        self._owner_check(op)

    def verify_owner(self, record: SourceClaimRecord, op: OperationContext) -> None:
        record = SourceClaimRecord.model_validate(record)
        self._owner_check(op)
        binding = record.binding
        if (binding.scope_id, binding.run, binding.task) != (
            self.scope_id,
            self.run,
            self.task,
        ):
            raise OwnershipConflict(
                "Claim record belongs to a different immutable original owner"
            )
