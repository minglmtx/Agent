"""Real local CAS/state with explicit unit engine/authority; no model or API."""

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.generator_model import (
    GeneratorMessage,
    GeneratorModelRequest,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
    LocalGeneratorIntent,
    LocalGeneratorOutput,
    LocalGeneratorFact,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.ports.local_generator import LocalGeneratorEngine
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_slurm_commands import Cancel
from test_construction_state import skill
from test_run_journal import command


class UnitEngine:
    def __init__(self) -> None:
        self.calls = 0
        self.validations = 0
        self.reject = False
        self.failure: BaseException | None = None
        self.output = LocalGeneratorOutput(
            text=json.dumps(skill("local").model_payload()),
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=20,
        )

    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        self.validations += 1
        if self.reject:
            raise ValueError("unit preflight rejected")

    def generate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.output

    def invoke(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        return self.generate(request, parameters, control)


class EngineeringInvocationEngine:
    """Lower engine check only; never production admission or captured proof."""

    def __init__(self, engine: LocalGeneratorEngine) -> None:
        self.engine = engine

    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        self.engine.validate(request, parameters, control)

    def invoke(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        return self.engine.generate(request, parameters, control)


class UnitAuthority:
    def __init__(self) -> None:
        self.denied = ""
        self.admissions = 0
        self.completions = 0

    def authorize_access(
        self,
        binding: LocalGeneratorBinding,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if self.denied == "access":
            raise OwnershipConflict("unit access denied")

    def authorize_generate(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        if self.denied == "generate":
            raise OwnershipConflict("unit generate denied")
        self.admissions += 1

    def verify_completion(
        self,
        fact: LocalGeneratorFact,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if self.denied == "completion":
            raise OwnershipConflict("unit completion denied")
        self.completions += 1


@dataclass
class Case:
    root: Path
    evidence: FileEvidenceStore
    binding: LocalGeneratorBinding
    request: GeneratorModelRequest
    operation: OperationContext
    engine: UnitEngine
    authority: UnitAuthority
    controls: OperationGuards

    def adapter(self) -> DurableGeneratorInference:
        return DurableGeneratorInference(
            self.root,
            self.binding,
            self.engine,
            self.evidence,
            self.controls,
            self.authority,
        )

    @cached_property
    def cleanup(self) -> OperationContext:
        return command("reconcile", cleanup_parent=self.operation.operation_id)


def case(root: Path) -> Case:
    evidence_root = root / "evidence"
    evidence_root.mkdir(exist_ok=True)
    state_root = root / "inference"
    state_root.mkdir(exist_ok=True)
    evidence = FileEvidenceStore(evidence_root)
    base = LocalGeneratorBaseParameters(
        max_input_tokens=100, max_new_tokens=100, top_p=0.95, enable_thinking=False
    )
    binding = LocalGeneratorBinding(
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id="unit-job", worker_id="unit-worker"
        ),
        source_task_id="source",
        release_ref=evidence.put(b"unit release", local_metadata("release-manifest/1")),
        model_binding_ref=evidence.put(
            b"unit model", local_metadata("model-binding/1")
        ),
        base_parameters_ref=evidence.put(
            base.model_dump_json().encode(), local_metadata("model-parameters/1")
        ),
    )
    request = GeneratorModelRequest(
        request_id="generate",
        generation_input_sha256="a" * 64,
        prompt_version="webarena-generator-v6-actor-capabilities",
        messages=(
            GeneratorMessage(role="system", content="system"),
            GeneratorMessage(role="user", content="任务"),
        ),
        seed=7,
        temperature=0.7,
    )
    return Case(
        state_root,
        evidence,
        binding,
        request,
        command("generate"),
        UnitEngine(),
        UnitAuthority(),
        OperationGuards(SystemClock(), Cancel()),
    )
