"""Actual Group source on the original single-task claim assembly.

The same controlled installed source reader supplies both context qualification
and task binding proofs. No local permission fallback, new source or ledger.
"""

from pathlib import Path
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedClosedSourceContexts,
    SupervisedSourceTaskBindingAuthority,
    SupervisedRunPlanInputChecks,
    SupervisedExecutionTaskSourceChecks,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedGroupReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from .gitlab_group_closed_source import ClosedGroupSourceContexts
from .execution_source_admission import (
    AdmittedExecutionSource,
    admit_closed_execution_source,
)


def admit_gitlab_group_execution_source(
    run: RunPlan,
    binding: RunBinding,
    material: ClosedGroupReadMaterial,
    execution: SlurmExecutionIdentity,
    controller: SlurmCgroupMembership,
    operation: OperationContext,
    *,
    claim_root: Path,
    claim_scope: str,
    evidence: EvidenceStore,
    controls: OperationControls,
    source_reads: ClosedSourceReadTransport,
) -> AdmittedExecutionSource:
    if not isinstance(source_reads, ClosedSourceReadTransport):
        raise TypeError("Original installed Group source reader is mandatory")
    run = RunPlan.model_validate(run)
    if len(run.tasks) != 1 or (
        run.tasks[0].identity.site,
        run.tasks[0].identity.family,
        run.tasks[0].identity.contract_version,
        run.tasks[0].identity.split,
    ) != ("gitlab", "group_creation", 1, "train"):
        raise OwnershipConflict("One original train Group family/version required")
    material = ClosedGroupReadMaterial.model_validate(material)
    contexts = ClosedGroupSourceContexts(
        SupervisedClosedSourceContexts(material, source_reads, controls),
        material.context_ref,
    )
    return admit_closed_execution_source(
        run,
        binding,
        contexts,
        execution,
        controller,
        operation,
        claim_root=claim_root,
        claim_scope=claim_scope,
        evidence=evidence,
        controls=controls,
        expected_site="gitlab",
        plan_input_checks=SupervisedRunPlanInputChecks(material, source_reads),
        source_checks=lambda authority: SupervisedExecutionTaskSourceChecks(
            authority, material, source_reads
        ),
        binding_load_checks=lambda authority: SupervisedSourceTaskBindingAuthority(
            authority, material, source_reads
        ),
        binding_authority=lambda authority: SupervisedSourceTaskBindingAuthority(
            authority, material, source_reads
        ),
    )
