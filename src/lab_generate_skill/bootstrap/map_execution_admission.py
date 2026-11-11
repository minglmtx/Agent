"""Original single Map source/claim assembly, before resource dispatch.

Trusted bootstrap supplies the persistent claim root/scope and exact RunBinding.
This composes existing ledgers and the actual Slurm claim authority; there is no
new namespace selection, fallback claim, runner or cached resource permission.
"""

from pathlib import Path
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
    SupervisedRunPlanInputChecks,
    SupervisedExecutionTaskSourceChecks,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from .execution_task_source import (
    publish_execution_task_source,
    PublishedExecutionTaskSource,
)
from .map_closed_source import (
    closed_map_source_contexts,
    ClosedMapSourceDeclarations,
    ClosedMapSourceContexts,
)


from .execution_source_admission import (
    AdmittedExecutionSource as AdmittedMapExecutionSource,
    admit_closed_execution_source,
)

__all__ = ["AdmittedMapExecutionSource", "admit_map_execution_source"]


def admit_map_execution_source(
    run: RunPlan,
    binding: RunBinding,
    declarations: ClosedMapSourceDeclarations,
    execution: SlurmExecutionIdentity,
    controller: SlurmCgroupMembership,
    operation: OperationContext,
    *,
    claim_root: Path,
    claim_scope: str,
    evidence: EvidenceStore,
    controls: OperationControls,
    source_reads: ClosedSourceReadTransport | None = None,
) -> AdmittedMapExecutionSource:
    run, binding = RunPlan.model_validate(run), RunBinding.model_validate(binding)
    run.check_binding(binding)
    if (
        run.purpose != "engineering"
        or run.split != "train"
        or len(run.tasks) != 1
        or run.tasks[0].identity.site != "map"
        or not isinstance(run.workload, ExecutionWorkload)
    ):
        raise OwnershipConflict("One original train Map engineering execution required")
    if (
        not isinstance(claim_root, Path)
        or claim_root.resolve(strict=True) != claim_root
    ):
        raise ValueError("Preprovisioned canonical persistent claim root required")
    contexts: ClosedMapSourceContexts
    if source_reads is None:
        contexts = closed_map_source_contexts(
            declarations, evidence, controls, operation
        )
    else:
        transport = source_reads
        material = ClosedMapReadMaterial.model_validate(vars(declarations))
        contexts = ClosedMapSourceContexts(
            SupervisedClosedSourceContexts(material, source_reads, controls),
            declarations.context_ref,
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
        expected_site="map",
        plan_input_checks=(
            None
            if source_reads is None
            else SupervisedRunPlanInputChecks(material, source_reads)
        ),
        source_checks=(
            None
            if source_reads is None
            else lambda authority: SupervisedExecutionTaskSourceChecks(
                authority, material, transport
            )
        ),
        binding_load_checks=(
            None
            if source_reads is None
            else lambda authority: SupervisedSourceTaskBindingAuthority(
                authority, material, transport
            )
        ),
        binding_authority=lambda authority: (
            OriginalSourceTaskBindingAuthority(
                authority, declarations.context_ref, contexts, evidence
            )
            if source_reads is None
            else SupervisedSourceTaskBindingAuthority(authority, material, source_reads)
        ),
    )
