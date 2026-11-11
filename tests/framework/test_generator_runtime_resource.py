"""Actual installed Slurm process/ledger, synthetic generation; no model loading."""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.models.generator_resource import registered_generator
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
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.models.generator_worker_exchange import (
    GeneratorWorkerExchange,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    GeneratorWorkerCommand,
    GeneratorWorkerReply,
)
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import LocalGeneratorParameters
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.bootstrap.generator_inference import bind_generator_inference
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.generator_admission import GeneratorCallInputs
from generator_resource_admission_fixtures import admission_case
from generator_resource_fixtures import ResourceCase
from local_generator_fixtures import case
from test_generator_resource import c as c, inspect
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


def test_actual_acquisition_to_durable_reply_and_closed_resource_replay(
    c: ResourceCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_root = tmp_path / "local"
    local_root.mkdir()
    local = case(local_root)
    # Production shares one OperationControls registry across both adapters.
    local.controls = c.controls
    local.binding = local.binding.model_copy(
        update={
            "owner": c.spec.token.owner,
            "release_ref": c.spec.release_ref,
            "model_binding_ref": c.spec.model_binding_ref,
            "base_parameters_ref": c.evidence.put(
                local.evidence.read(local.binding.base_parameters_ref),
                local_metadata("model-parameters/1"),
            ),
        }
    )
    records_root = tmp_path / "executions"
    records_root.mkdir()
    records = FileGeneratorExecutions(records_root, c.evidence)
    calls: list[str] = []
    with registered_generator(c.spec, c.op, **c.dependencies()) as engine:
        scope = GeneratorExecutionScope(
            local.binding,
            c.spec,
            c.journal,
            c.evidence,
            engine,
            local.operation,
            local.controls.bind(local.operation),
        )

        def generate(
            request: GeneratorModelRequest,
            params: LocalGeneratorParameters,
            control: OperationControl,
        ) -> GeneratorWorkerExchange:
            calls.append(request.request_id)
            command = GeneratorWorkerCommand(
                session_id=c.spec.token.expected_resource_id,
                sequence=2 + len(calls),
                operation="generate",
                remaining_seconds=control.checkpoint(),
                request=request,
                parameters=params,
            )
            reply = GeneratorWorkerReply(
                session_id=command.session_id,
                sequence=command.sequence,
                operation="generate",
                command_sha256=command.digest,
                status="ok",
                output=local.engine.output,
            )
            return GeneratorWorkerExchange(
                command.model_dump_json().encode(), reply.model_dump_json().encode()
            )

        monkeypatch.setattr(engine, "generate_exchange", generate)
        monkeypatch.setattr(engine, "validate", lambda *args: None)
        actual = ResourceGeneratorExecutionAuthority(scope, records)
        inference = DurableGeneratorInference(
            local.root,
            local.binding,
            ResourceGeneratorInvocation(scope, records),
            c.evidence,
            local.controls,
            actual,
        )
        ref = inference.generate(local.request, local.operation)
        assert (
            inference.generate(local.request, local.operation) == ref
            and len(calls) == 1
        )
        # The production assembly must preserve its business admission layer.
        admission = admission_case(c, tmp_path / "business")

        class DenyConstruction:
            def read(self, op: object) -> object:
                raise OwnershipConflict("business scope deliberately unqualified")

        bound = bind_generator_inference(
            root=local.root,
            records_root=records_root,
            binding=local.binding,
            spec=c.spec,
            resources=c.journal,
            evidence=c.evidence,
            engine=engine,
            operation=local.operation,
            controls=local.controls,
            run=admission.run,
            construction=cast(ConstructionJournal, DenyConstruction()),
            runs=admission.deps.runs,
            inputs=cast(GeneratorCallInputs, object()),
        )
        with pytest.raises(OwnershipConflict, match="unqualified"):
            bound.generate(
                local.request.model_copy(update={"request_id": "new-request"}),
                local.operation.model_copy(update={"operation_id": "new-operation"}),
            )
        assert len(calls) == 1
    assert inspect(c).state == "closed"
    assert inference.generate(local.request, local.operation) == ref and len(calls) == 1
    with pytest.raises(OwnershipConflict, match="no longer acquired"):
        inference.generate(
            local.request.model_copy(update={"request_id": "after-close"}),
            local.operation.model_copy(update={"operation_id": "after-close"}),
        )
    assert len(calls) == 1
