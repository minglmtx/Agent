"""Synthetic wire/acquired evidence on a real CAS; no model or permission claim."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.generator_executions import (
    FileGeneratorExecutions,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    GeneratorWorkerCommand,
    GeneratorWorkerReply,
)
from lab_generate_skill.adapters.models.generator_resource_records import fact
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.slurm.step_launch import generator_step_name
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.generator_execution import GeneratorExecutionRecord
from lab_generate_skill.domain.generator_step import GeneratorStepStarted
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorIntent,
    LocalGeneratorOutput,
    LocalGeneratorParameters,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from generator_resource_fixtures import resource_case
from local_generator_fixtures import case
from cgroup_fixtures import Control


@dataclass
class ExecutionCase:
    root: Path
    store: FileEvidenceStore
    record: GeneratorExecutionRecord
    output: LocalGeneratorOutput

    @property
    def adapter(self) -> FileGeneratorExecutions:
        return FileGeneratorExecutions(self.root, self.store)

    def put(self, raw: bytes, schema: str) -> EvidenceRef:
        return self.store.put(raw, local_metadata(schema))


@pytest.fixture(scope="module")
def execution_template(tmp_path_factory: pytest.TempPathFactory) -> ExecutionCase:
    root = tmp_path_factory.mktemp("execution-template")
    c = resource_case(root / "resource", Path("/test/python"))
    (root / "local").mkdir()
    local = case(root / "local")
    base = c.evidence.put(
        local.evidence.read(local.binding.base_parameters_ref),
        local_metadata("model-parameters/1"),
    )
    binding = local.binding.model_copy(
        update={
            "owner": c.spec.token.owner,
            "release_ref": c.spec.release_ref,
            "model_binding_ref": c.spec.model_binding_ref,
            "base_parameters_ref": base,
        }
    )
    params = LocalGeneratorParameters(
        max_input_tokens=100,
        max_new_tokens=100,
        top_p=0.95,
        enable_thinking=False,
        seed=local.request.seed,
        temperature=local.request.temperature,
    )
    intent = LocalGeneratorIntent(
        binding=binding,
        request_id=local.request.request_id,
        request_ref=c.evidence.put(
            local.request.model_dump_json().encode(),
            local_metadata("generator-model-request/1"),
        ),
        parameters_ref=c.evidence.put(
            params.model_dump_json().encode(), local_metadata("model-parameters/1")
        ),
        operation=local.operation,
    )
    controller = c.spec.slurm.allocation.facts.writer
    guard = ProcessOwnerGuard(
        controller=controller,
        supervisor=controller.model_copy(
            update={"process_id": controller.process_id + 10000000}
        ),
        worker=controller.model_copy(
            update={"process_id": controller.process_id + 10000001}
        ),
    )
    cg = c.spec.slurm.allocation.facts.cgroup
    worker = cg.model_copy(
        update={
            "writer": guard.worker,
            "step_id": "0",
            "user_path": cg.user_path.replace("step_batch", "step_0"),
            "user_inode": cg.user_inode + 100,
            "task_inode": cg.task_inode + 101,
        }
    )
    target = SlurmStepTarget(
        resources="single_gpu",
        execution=c.spec.slurm.allocation.facts.execution,
        step_name=generator_step_name(c.spec.token),
        launcher=controller.model_copy(
            update={"process_id": controller.process_id + 10000002}
        ),
        worker=worker,
    )
    started = GeneratorStepStarted(
        allocation=c.spec.slurm.allocation,
        controller=SlurmControllerStep(
            target=target,
            started_at_epoch=target.execution.started_at_epoch,
            gpu_type=c.spec.slurm.allocation.facts.controller.gpu_type,
            memory="1M",
        ),
        evidence=c.evidence.put(
            b"synthetic raw", local_metadata("generator-step-raw/1")
        ),
    )
    acquired = fact(
        c.evidence,
        c.spec,
        c.op,
        "acquired",
        {
            "owner_guard": guard.model_dump(mode="json"),
            "worker": guard.worker.model_dump(mode="json"),
            "step": started.model_dump(mode="json"),
        },
        control=Control(),
    )
    command = GeneratorWorkerCommand(
        session_id=c.spec.token.expected_resource_id,
        sequence=3,
        operation="generate",
        remaining_seconds=5.0,
        request=local.request,
        parameters=params,
    )
    output = LocalGeneratorOutput(
        text="recorded", finish_reason="stop", prompt_tokens=10, completion_tokens=3
    )
    reply = GeneratorWorkerReply(
        session_id=command.session_id,
        sequence=command.sequence,
        operation="generate",
        command_sha256=command.digest,
        status="ok",
        output=output,
    )
    record = GeneratorExecutionRecord(
        intent=intent,
        resource=c.spec.token,
        spec_ref=c.evidence.put(
            c.spec.model_dump_json().encode(),
            local_metadata("generator-resource-spec/3"),
        ),
        acquired_ref=acquired,
        command_ref=c.evidence.put(
            command.model_dump_json().encode(),
            local_metadata("generator-worker-command/3"),
        ),
        reply_ref=c.evidence.put(
            reply.model_dump_json().encode(), local_metadata("generator-worker-reply/4")
        ),
        guard=guard,
    )
    return ExecutionCase(root, c.evidence, record, output)


@pytest.fixture
def e(tmp_path: Path, execution_template: ExecutionCase) -> ExecutionCase:
    shutil.copytree(execution_template.store._blobs.parent, tmp_path / "evidence")
    (tmp_path / "records").mkdir()
    return ExecutionCase(
        tmp_path / "records",
        FileEvidenceStore(tmp_path / "evidence"),
        execution_template.record,
        execution_template.output,
    )
