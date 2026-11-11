"""Original single-task claim assembly, independent of site business codecs.

The site wrapper supplies its exact closed reader and binding verifier. This
retains the existing actual-caller check before plan publication, original claim
namespace/once rules, and original execution source publisher. No new ledger.
"""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Literal
from lab_generate_skill.ports.task_bindings import (
    TaskBindingAuthority,
    TaskBindingLoadChecks,
)
from pathlib import Path
from lab_generate_skill.ports.run_plan import RunPlanInputChecks
from lab_generate_skill.ports.execution_task import ExecutionTaskSourceChecks
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.source_task_binding_authority import (
    OriginalSourceTaskBindingAuthority,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedClosedSourceContexts,
    SupervisedSourceTaskBindingAuthority,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from .execution_task_source import (
    publish_execution_task_source,
    PublishedExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts


@dataclass(frozen=True)
class AdmittedExecutionSource:
    authority: OriginalExecutionClaimAuthority
    plans: EvidenceRunPlans
    claims: FileSourceClaims
    claim: SourceClaimReceipt
    bindings: EvidenceTaskBindings
    contexts: ClosedSourceContexts
    reader: OriginalExecutionTaskSource
    published: PublishedExecutionTaskSource


def admit_closed_execution_source(
    run: RunPlan,
    binding: RunBinding,
    contexts: ClosedSourceContexts,
    execution: SlurmExecutionIdentity,
    controller: SlurmCgroupMembership,
    operation: OperationContext,
    *,
    claim_root: Path,
    claim_scope: str,
    evidence: EvidenceStore,
    controls: OperationControls,
    expected_site: Literal["map", "shopping_admin", "gitlab", "shopping"],
    plan_input_checks: RunPlanInputChecks | None = None,
    binding_load_checks: (
        Callable[[OriginalExecutionClaimAuthority], TaskBindingLoadChecks] | None
    ) = None,
    source_checks: (
        Callable[[OriginalExecutionClaimAuthority], ExecutionTaskSourceChecks] | None
    ) = None,
    binding_authority: Callable[
        [OriginalExecutionClaimAuthority], TaskBindingAuthority
    ],
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
        raise OwnershipConflict(
            "One original train engineering execution for the selected site required"
        )
    if (
        not isinstance(claim_root, Path)
        or claim_root.resolve(strict=True) != claim_root
    ):
        raise ValueError("Preprovisioned canonical persistent claim root required")
    if not isinstance(contexts, ClosedSourceContexts) or not callable(
        binding_authority
    ):
        raise TypeError(
            "Original closed source reader and binding permission supplier required"
        )
    plans = EvidenceRunPlans(evidence, controls, input_checks=plan_input_checks)
    authority = OriginalExecutionClaimAuthority(
        claim_scope,
        binding,
        run.tasks[0],
        execution,
        controller,
        evidence=evidence,
        plans=plans,
        contexts=contexts,
        controls=controls,
    )
    # Verify the actual original caller before even immutable plan publication.
    authority.require_caller(operation)
    plan_op = operation.model_copy(
        update={"operation_id": operation.operation_id + ".plan"}
    )
    claim_op = operation.model_copy(
        update={"operation_id": operation.operation_id + ".claim"}
    )
    source_op = operation.model_copy(
        update={"operation_id": operation.operation_id + ".source"}
    )
    if plans.publish(run, plan_op) != binding.plan_ref:
        raise OwnershipConflict("Publication changed original frozen RunPlan")
    claims = FileSourceClaims(
        claim_root, claim_scope, controls, evidence, plans, authority
    )
    claim = claims.claim(
        SourceClaimBinding(scope_id=claim_scope, run=binding, task=run.tasks[0]),
        claim_op,
    )
    bindings = EvidenceTaskBindings(
        evidence,
        controls,
        binding_authority(authority),
        load_checks=(
            None if binding_load_checks is None else binding_load_checks(authority)
        ),
    )
    reader = OriginalExecutionTaskSource(
        plans,
        claims,
        contexts,
        bindings,
        evidence,
        source_checks=None if source_checks is None else source_checks(authority),
    )
    published = publish_execution_task_source(
        binding,
        claim.reference,
        source_op,
        reader=reader,
        evidence=evidence,
        controls=controls,
    )
    return AdmittedExecutionSource(
        authority, plans, claims, claim, bindings, contexts, reader, published
    )
