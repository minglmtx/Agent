"""Actual Shopping category source on the original single-task claim assembly.

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
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from .shopping_category_closed_source import ClosedCategoryNavigationSourceContexts
from .execution_source_admission import (
    AdmittedExecutionSource,
    admit_closed_execution_source,
)


def admit_shopping_category_execution_source(
    run: RunPlan,
    binding: RunBinding,
    material: ClosedCategoryNavigationReadMaterial,
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
        raise TypeError(
            "Original installed Shopping category source reader is mandatory"
        )
    material = ClosedCategoryNavigationReadMaterial.model_validate(material)
    contexts = ClosedCategoryNavigationSourceContexts(
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
        expected_site="shopping",
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
