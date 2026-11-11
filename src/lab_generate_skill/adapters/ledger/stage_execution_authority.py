"""Actual current Slurm controller and bounded corrected-stage plan admission.

Uses unchanged original caller checks, actual parent evidence and the same
canonical claim root. Neither a declaration nor the parent grants execution.
"""

from pathlib import Path
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimRecord,
    check_claim_operation,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.adapters.plans.stage_parent import RetainedStageParentChecks
from lab_generate_skill.adapters.plans.prior_stage_review import PriorStageReviewChecks
from .execution_claim_authority import OriginalExecutionClaimAuthority


class StageExecutionClaimAuthority(OriginalExecutionClaimAuthority):
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
        parent: RetainedStageParentChecks,
        claim_root: Path,
    ) -> None:
        super().__init__(
            scope_id,
            run,
            task,
            execution,
            controller,
            evidence=evidence,
            plans=plans,
            contexts=contexts,
            controls=controls,
        )
        if (
            not isinstance(parent, RetainedStageParentChecks)
            or not isinstance(claim_root, Path)
            or claim_root.resolve(strict=True) != claim_root
        ):
            raise TypeError(
                "Actual retained parent checker and canonical claim root required"
            )
        self.parent, self.claim_root = parent, claim_root
        self.origin: FrozenExecutionOrigin = parent.origin
        self.prior_reviews = PriorStageReviewChecks(parent)
        expected = SourceClaimBinding(scope_id=scope_id, run=run, task=task)
        if (
            parent.binding != expected
            or self.origin.validation.schema_version != "source-stage-validation/2"
        ):
            raise OwnershipConflict(
                "Formal stage admission requires exact scoped v2 validation"
            )

    def authorize_create(
        self, binding: SourceClaimBinding, plan: RunPlan, op: OperationContext
    ) -> None:
        raise OwnershipConflict(
            "Stage admission must use its explicit validation ledger"
        )

    def _peers(self, op: OperationContext) -> None:
        control = self.controls.bind(op)
        validation = self.origin.validation
        legacy = sorted(self.claim_root.glob("*.stage-validation-claim.json"))
        if len(legacy) > 4096:
            raise EvidenceIntegrityError(
                "Legacy stage history exceeds its bounded root"
            )
        for path in legacy:
            control.checkpoint()
            if path.is_symlink() or path.stat().st_size > 128 * 1024:
                raise EvidenceIntegrityError("Unsafe legacy stage history")
            record = SourceClaimRecord.model_validate_json(path.read_bytes())
            if record.binding.key == self.parent.binding.key:
                raise OwnershipConflict(
                    "Original legacy validation outcome must be reviewed before migration"
                )
        paths = sorted(self.claim_root.glob(validation.parent_prefix + "*.json"))
        if len(paths) > 128:
            raise EvidenceIntegrityError(
                "Stage validation history exceeds its bounded scope"
            )
        references = (
            self.parent.data(op).authorization.closed_prior_stage_refs
            if validation.authorization_ref.content_schema
            in (
                "task-stage-validation-authorization/2",
                "task-stage-validation-authorization/3",
                "task-stage-validation-authorization/4",
            )
            else ()
        )
        consumed: set[EvidenceRef] = set()
        for path in paths:
            control.checkpoint()
            if path.is_symlink() or path.stat().st_size > 128 * 1024:
                raise EvidenceIntegrityError("Unsafe stage validation history")
            raw = path.read_bytes()
            record = SourceClaimRecord.model_validate_json(raw)
            if record.binding != self.parent.binding:
                # A different release/owner is never an automatic replay. Its
                # original outcome/unknown/closure must be reviewed separately.
                if not references:
                    raise OwnershipConflict(
                        "Prior stage validation requires original outcome/closure review"
                    )
                consumed.add(
                    self.prior_reviews.verify_peer(
                        record, raw, references, self.run, control
                    )
                )
            if path.read_bytes() != raw:
                raise EvidenceIntegrityError(
                    "Canonical prior stage changed during review"
                )
        if consumed != set(references):
            raise OwnershipConflict(
                "Selected prior review does not match canonical peer history"
            )
        for marker in self.claim_root.glob(
            validation.parent_prefix + "*.json.initialized"
        ):
            control.checkpoint()
            payload = marker.with_name(marker.name.removesuffix(".initialized"))
            if payload.name != validation.filename and not payload.exists():
                raise EvidenceIntegrityError(
                    "Prior stage commit is unresolved; do not change target/owner"
                )

    def verify_parent(
        self, validation: SourceStageValidation, operation: OperationContext
    ) -> None:
        self._owner_check(operation)
        self.parent.verify_parent(validation, operation)
        self._peers(operation)

    def authorize_current(
        self,
        validation: SourceStageValidation,
        binding: SourceClaimBinding,
        plan: RunPlan,
        operation: OperationContext,
    ) -> None:
        check_claim_operation(binding, operation, creating=True)
        self.verify_parent(validation, operation)
        control = self.controls.bind(operation)
        if (
            binding != self.parent.binding
            or self.plans.load(self.run, operation) != plan
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
                "Stage plan must remain exact unpaid train/Actor-only engineering"
            )
        inputs = self.reads.parse(
            plan.workload.task_inputs_ref,
            "execution-task-inputs/1",
            ExecutionTaskInputs,
            control,
        )
        policy = self.reads.parse(
            plan.workload.execution_policy_ref,
            "engineering-execution-policy/3",
            EngineeringActorPolicy,
            control,
        )
        projection = policy.actor_projection
        if (
            not isinstance(projection, AdaptiveObservationProjection)
            or not projection.supports_local(self.task.identity)
            or projection.read_policy.schema_version != "observation-read-policy/2"
            or projection.read_policy.max_consecutive_invalid_proposals != 3
            or projection.read_policy.max_identical_invalid_proposals != 3
        ):
            raise OwnershipConflict(
                "Corrected-stage validation requires the selected explicit 3/3 policy"
            )
        cfg = self.reads.parse(
            policy.actor_context_ref,
            "actor-context-configuration/1",
            ActorContextConfiguration,
            control,
        )
        model = plan.models[0]
        if not any(
            profile.routing_ref == model.model_binding_ref
            and profile.configuration_ref == model.parameters_ref
            for profile in cfg.profiles
        ) or any(
            profile.context_window != 65536
            or profile.output_reserve != 4096
            or profile.input_limit
            > min(61440, 65536 - 4096 - profile.uncounted_overhead)
            for profile in cfg.profiles
        ):
            raise OwnershipConflict(
                "Stage Actor must retain its exact 64K/O4096 profile"
            )
        facts = self.parent.data(operation)
        context: PublicContextReceipt = self.contexts.load_context(
            inputs.source_context_receipt_ref, operation
        )
        task = self.reads.parse(
            inputs.task_binding_ref, "task-binding/1", TaskBinding, control
        )
        if (
            context != facts.context
            or inputs.source_context_receipt_ref
            != facts.source.source_context_receipt_ref
            or inputs.attempt_id
            in (context.scope.attempt_id, facts.source.intent.binding.attempt_id)
            or task != self.task
            or policy.skill.model_dump_json().encode()
            != self.reads.read(inputs.skill_ref, control)
            or policy.max_generations
            != plan.resources.max_actor_generations_per_attempt
            or policy.max_interactions != plan.resources.max_interactions_per_attempt
            or policy.memory != plan.policies.actor_memory
        ):
            raise OwnershipConflict(
                "Stage policy/private task changed original frozen source binding"
            )
        self._owner_check(operation)

    def verify_current(
        self,
        validation: SourceStageValidation,
        record: SourceClaimRecord,
        operation: OperationContext,
    ) -> None:
        self.verify_parent(validation, operation)
        super().verify_owner(record, operation)
