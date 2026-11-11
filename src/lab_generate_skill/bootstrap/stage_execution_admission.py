"""Explicit corrected-Actor admission; ordinary closed-source admission is unchanged.

The retained source remains under its original owner. This entry verifies real
parent bodies and current Slurm caller before publishing the selected plan and
claiming its separate, parent-scoped validation slot. It creates no native site,
initialization, Actor, review or training permission by itself.
"""

from pathlib import Path
from typing import Literal
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.adapters.ledger.stage_execution_authority import (
    StageExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.stage_parent import RetainedStageParentChecks
from lab_generate_skill.adapters.plans.stage_validation_source import (
    SupervisedStageValidationContexts,
    SupervisedStageValidationBindingAuthority,
    SupervisedStageValidationSourceChecks,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from .execution_source_admission import AdmittedExecutionSource
from .execution_task_source import publish_execution_task_source


def admit_stage_validation_source(
    run: RunPlan,
    binding: RunBinding,
    origin: FrozenExecutionOrigin,
    material: ClosedSourceMaterial,
    transport: ClosedSourceReadTransport,
    execution: SlurmExecutionIdentity,
    controller: SlurmCgroupMembership,
    operation: OperationContext,
    *,
    authorization_id: str,
    claim_root: Path,
    claim_scope: str,
    evidence: EvidenceStore,
    controls: OperationControls,
    expected_site: Literal["map", "shopping_admin"],
    contexts_type: type[ClosedSourceContexts] = ClosedSourceContexts,
) -> AdmittedExecutionSource:
    run, binding = RunPlan.model_validate(run), RunBinding.model_validate(binding)
    run.check_binding(binding)
    if (
        run.purpose != "engineering"
        or run.split != "train"
        or len(run.tasks) != 1
        or run.tasks[0].identity.site != expected_site
        or not isinstance(run.workload, ExecutionWorkload)
    ):
        raise OwnershipConflict("Exact held-site train engineering stage plan required")
    if (
        not isinstance(claim_root, Path)
        or claim_root.resolve(strict=True) != claim_root
    ):
        raise ValueError("Preprovisioned canonical persistent claim root required")
    if transport.store is not evidence:
        raise OwnershipConflict(
            "Parent proof and current checks require the same store"
        )
    current = SourceClaimBinding(scope_id=claim_scope, run=binding, task=run.tasks[0])
    parent = RetainedStageParentChecks(
        origin, current, authorization_id, evidence, controls, current_checks=transport
    )
    records = SupervisedStageValidationContexts(
        material, transport, controls, current, origin, parent
    )
    if not isinstance(contexts_type, type) or not issubclass(
        contexts_type, ClosedSourceContexts
    ):
        raise TypeError("Original closed-source context wrapper required")
    contexts = contexts_type(records, material.context_ref)
    # Plan input bodies are checked directly. Ordinary same-owner supervised
    # plan-input readers remain unchanged and cannot retag the old material.
    plans = EvidenceRunPlans(evidence, controls)
    authority = StageExecutionClaimAuthority(
        claim_scope,
        binding,
        run.tasks[0],
        execution,
        controller,
        evidence=evidence,
        plans=plans,
        contexts=contexts,
        controls=controls,
        parent=parent,
        claim_root=claim_root,
    )
    authority.require_caller(operation)
    authority.verify_parent(origin.validation, operation)
    if (
        plans.publish(
            run,
            operation.model_copy(
                update={"operation_id": operation.operation_id + ".plan"}
            ),
        )
        != binding.plan_ref
    ):
        raise OwnershipConflict("Stage publication changed the selected frozen RunPlan")
    claims = FileSourceStageValidations(
        claim_root,
        claim_scope,
        controls,
        evidence,
        plans,
        authority,
        validation=origin.validation,
    )
    claim = claims.claim(
        current,
        operation.model_copy(
            update={"operation_id": operation.operation_id + ".claim"}
        ),
    )
    binding_authority = SupervisedStageValidationBindingAuthority(authority, records)
    bindings = EvidenceTaskBindings(
        evidence, controls, binding_authority, load_checks=binding_authority
    )
    reader = OriginalExecutionTaskSource(
        plans,
        claims,
        contexts,
        bindings,
        evidence,
        source_checks=SupervisedStageValidationSourceChecks(authority, records),
    )
    published = publish_execution_task_source(
        binding,
        claim.reference,
        operation.model_copy(
            update={"operation_id": operation.operation_id + ".source"}
        ),
        reader=reader,
        evidence=evidence,
        controls=controls,
        frozen_origin=origin,
    )
    return AdmittedExecutionSource(
        authority, plans, claims, claim, bindings, contexts, reader, published
    )
