"""Compose durable inference with mandatory business and actual resource checks.

The caller has already selected/authorized the run, source and original resource.
This is not a submit entry or permission loader. There is no unit-authority or
raw-engine fallback; acquisition and independent recovery remain separate.
"""

from pathlib import Path
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.local_generator import LocalGeneratorBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.generator_admission import GeneratorCallInputs
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.application.generator_admission import (
    ConstructionGeneratorAuthority,
    GeneratorAdmissionDeps,
)
from lab_generate_skill.adapters.models.generator_execution_scope import (
    GeneratorExecutionScope,
)
from lab_generate_skill.adapters.models.generator_execution_authority import (
    ResourceGeneratorExecutionAuthority,
)
from lab_generate_skill.adapters.models.generator_invocation import (
    ResourceGeneratorInvocation,
)
from lab_generate_skill.adapters.models.generator_executions import (
    FileGeneratorExecutions,
)
from lab_generate_skill.adapters.models.generator_worker_client import (
    SupervisedGeneratorEngine,
)
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference


def bind_generator_inference(
    *,
    root: Path,
    records_root: Path,
    binding: LocalGeneratorBinding,
    spec: GeneratorResourceSpec,
    resources: ResourceJournal,
    evidence: EvidenceStore,
    engine: SupervisedGeneratorEngine,
    operation: OperationContext,
    controls: OperationControls,
    run: RunBinding,
    construction: ConstructionJournal,
    runs: RunJournal,
    inputs: GeneratorCallInputs,
) -> DurableGeneratorInference:
    control = controls.bind(operation)
    scope = GeneratorExecutionScope(
        binding, spec, resources, evidence, engine, operation, control
    )
    records = FileGeneratorExecutions(records_root, evidence)
    actual = ResourceGeneratorExecutionAuthority(scope, records)
    authority = ConstructionGeneratorAuthority(
        run, GeneratorAdmissionDeps(construction, runs, inputs, actual)
    )
    authority.authorize_access(binding, operation, control)
    return DurableGeneratorInference(
        root,
        binding,
        ResourceGeneratorInvocation(scope, records),
        evidence,
        controls,
        authority,
    )
