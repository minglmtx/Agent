"""Explicit composition for a previously selected resource/run scope.

This is not a public submit command or approval/current-release loader. The
trusted enclosing workflow must authorize/pin its scope before calling it and
provide hard supervision. Engineering callers must retain their engineering
label; no fixture authority, fallback, model request or external effect here.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.models.generator_resource_authority import (
    PinnedSlurmGeneratorAuthority,
)
from lab_generate_skill.application.generator_resource_admission import (
    RunGeneratorResourceAuthority,
    GeneratorResourceAdmissionDeps,
)


@dataclass(frozen=True)
class GeneratorResourceAuthorities:
    admission: RunGeneratorResourceAuthority
    actual: PinnedSlurmGeneratorAuthority


def bind_generator_resource_authority(
    spec: GeneratorResourceSpec,
    startup: OperationContext,
    *,
    run: RunBinding,
    plans: RunPlans,
    runs: RunJournal,
    evidence: EvidenceStore,
    workspace_root: Path,
    allocation_verifier: SlurmAllocationVerifier,
) -> GeneratorResourceAuthorities:
    actual = PinnedSlurmGeneratorAuthority(
        spec,
        startup,
        workspace_root=workspace_root,
        evidence=evidence,
        allocation_verifier=allocation_verifier,
    )
    admission = RunGeneratorResourceAuthority(
        run, GeneratorResourceAdmissionDeps(plans, runs, evidence, actual)
    )
    return GeneratorResourceAuthorities(admission, actual)
