"""Registered actual GPU child, original durable replay and persisted closure.

Actual resource authority in engineering scope; no formal data or paid calls.
"""

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
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.generator_resource import registered_generator
from lab_generate_skill.adapters.models.generator_worker_client import (
    SupervisedGeneratorEngine,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import decode_command
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.processes.capture import retained_capture
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.domain.generator_model_binding import GeneratorModelBinding
from lab_generate_skill.domain.generator_step import (
    GeneratorStepStarted,
    GeneratorStepClosed,
)
from lab_generate_skill.domain.generator_model import (
    GeneratorMessage,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
)
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.errors import (
    GeneratorInputBudgetExceeded,
    DispatchAlreadyCommitted,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from generator_engine_live import staging, verify_source, W
from generator_model_assets import pinned_model
from generator_resource_fixtures import resource_case
from generator_resource_admission_fixtures import admission_case
from lab_generate_skill.bootstrap.generator_resource import (
    bind_generator_resource_authority,
)
from generator_release_fixtures import (
    freeze_model_release,
    metadata as release_metadata,
)
from generator_worker_diagnostics import record_failure
from local_generator_fixtures import case
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_registered_actual_gpu(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = Path(os.environ["LAB_WORKER_SOFTWARE_RECEIPT"])
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    verify_source(receipt)
    c = resource_case(
        output / "resource",
        installed_sources.executable,
        installation=installed_sources,
    )
    c.op = c.op.model_copy(
        update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=700)}
    )
    control = c.controls.bind(c.op)
    inference_root = output / "inference"
    inference_root.mkdir()
    local = case(inference_root)
    local.controls = c.controls
    # This operation is not yet bound/used; choose its engineering budget before
    # model staging and loading rather than extending an existing deadline.
    local.operation = local.operation.model_copy(
        update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=700)}
    )
    request = local.request.model_copy(
        update={
            "messages": (
                GeneratorMessage(
                    role="system",
                    content="Reply with exactly the requested short text.",
                ),
                GeneratorMessage(role="user", content="Say exactly: Hello world."),
            )
        }
    )
    base = LocalGeneratorBaseParameters(
        max_input_tokens=512, max_new_tokens=16, top_p=0.9, enable_thinking=False
    )
    parameters = LocalGeneratorParameters(
        **base.model_dump(exclude={"schema_version"}),
        seed=request.seed,
        temperature=request.temperature,
    )
    commands: list[str] = []
    original_exchange = FramedProcessSession.exchange

    def observed_exchange(
        self: FramedProcessSession, payload: bytes, guard: OperationControl
    ) -> bytes:
        commands.append(decode_command(payload).operation)
        return original_exchange(self, payload, guard)

    monkeypatch.setattr(FramedProcessSession, "exchange", observed_exchange)
    artifact, inventory_sha = pinned_model(W)
    publication_root = W / "assets/frozen-generator-models-20261026-v1"
    publication_root.mkdir(exist_ok=True)
    artifact = FileArtifactFreezer(W, publication_root).freeze(
        artifact, "qwen3-8b-" + inventory_sha[:16], control
    )
    config = c.spec.engine_config.model_copy(update={"context_window": 40960})
    release_ref, model_ref = freeze_model_release(
        output / "actual-model-release",
        c.evidence,
        artifact,
        config,
        model_name="Qwen/Qwen3-8B",
        installation=installed_sources.manifest,
    )
    c.workspace_root = W
    model_binding = GeneratorModelBinding.model_validate_json(
        c.evidence.read(model_ref)
    )
    for reference in (release_ref, model_ref, model_binding.engine_config_ref):
        assert (
            local.evidence.put(
                c.evidence.read(reference), release_metadata(reference.content_schema)
            )
            == reference
        )
    safe_to_remove = True
    engine: SupervisedGeneratorEngine | None = None
    with staging(preserve_if=lambda: not safe_to_remove) as staged:
        for file in artifact.files:
            copy_pinned_file(Path(artifact.root), staged, file, control)
        staged.chmod(0o555)
        c.spec = c.spec.model_copy(
            update={
                "artifact": ReleaseArtifact(
                    artifact_id=artifact.artifact_id,
                    root=str(staged),
                    files=artifact.files,
                ),
                "engine_config": config,
                "release_ref": release_ref,
                "model_binding_ref": model_ref,
            }
        )
        binding = local.binding.model_copy(
            update={
                "owner": c.spec.token.owner,
                "base_parameters_ref": c.evidence.put(
                    base.model_dump_json().encode(),
                    local_metadata("model-parameters/1"),
                ),
                "model_binding_ref": model_ref,
                "release_ref": release_ref,
            }
        )
        admission = admission_case(c, output / "run-state")
        authorities = bind_generator_resource_authority(
            c.spec,
            c.op,
            run=admission.run,
            plans=admission.deps.plans,
            runs=admission.deps.runs,
            evidence=c.evidence,
            workspace_root=c.workspace_root,
            allocation_verifier=c.allocation_verifier,
        )
        dependencies = c.dependencies()
        dependencies["authority"] = authorities.admission
        safe_to_remove = False
        try:
            with registered_generator(c.spec, c.op, **dependencies) as engine:
                engine.validate(request, parameters, control)
                first = engine.generate(request, parameters, control)
                assert engine.generate(request, parameters, control) == first
                with pytest.raises(GeneratorInputBudgetExceeded):
                    engine.validate(
                        request,
                        parameters.model_copy(update={"max_input_tokens": 1}),
                        control,
                    )
                records_root = output / "executions"
                records_root.mkdir()
                records = FileGeneratorExecutions(records_root, c.evidence)
                scope = GeneratorExecutionScope(
                    binding,
                    c.spec,
                    c.journal,
                    c.evidence,
                    engine,
                    local.operation,
                    local.controls.bind(local.operation),
                )
                runtime_authority = ResourceGeneratorExecutionAuthority(scope, records)
                inference = DurableGeneratorInference(
                    local.root,
                    binding,
                    ResourceGeneratorInvocation(scope, records),
                    c.evidence,
                    local.controls,
                    runtime_authority,
                )
                ref = inference.generate(request, local.operation)
                count = commands.count("generate")
                assert inference.generate(request, local.operation) == ref
                assert commands.count("generate") == count == 3
                completion = GeneratorTextCompletion.model_validate_json(
                    c.evidence.read(ref)
                )
                assert completion.text == first.text
            snapshot = inference.inspect(request, local.operation)
            execution = records.load(
                snapshot.intent, local.controls.bind(local.operation)
            )
            closed_count = len(commands)
            assert inference.generate(request, local.operation) == ref
            assert len(commands) == closed_count
            assert local.authority.completions == local.authority.admissions == 0
            record = c.journal.read(
                c.spec.token,
                c.op.cleanup(
                    "inspect-live", now=datetime.now(timezone.utc), seconds=30
                ),
            )
            assert [e.state for e in record.events] == [
                "registered",
                "acquiring",
                "acquired",
                "closing",
                "closed",
            ]
            for event in record.events:
                for proof in event.evidence:
                    c.evidence.read(proof)
            acquired = json.loads(c.evidence.read(record.events[2].evidence[0]))
            ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
            started = GeneratorStepStarted.model_validate_json(
                json.dumps(acquired["step"])
            )
            closed = GeneratorStepClosed.model_validate_json(
                json.dumps(ending["step_closed"])
            )
            assert closed.target == started.controller.target
            assert authorities.actual.started is not None
            assert closed.target == authorities.actual.started.controller.target
            assert closed == authorities.actual.closed
            for proof in authorities.actual.observations:
                c.evidence.read(proof)
            assert len(authorities.actual.observations) == 3
            assert not c.authority.workers and not c.authority.closed
            assert (
                closed.target.launcher.process_id
                != closed.target.worker.writer.process_id
            )
            assert (
                ending["termination"]["process_id"] == closed.target.launcher.process_id
            )
            assert ending["termination"]["state"] == "reaped"
            assert ending["cleanup_errors"] == [] and ending["primary"] is None
            for observed in (started, closed):
                c.evidence.read(observed.evidence)
            # Only the acknowledged original step/tree closure permits removal.
            # A reaped srun alone does not prove the actual worker has stopped.
            safe_to_remove = True
            before = len(commands)
            with pytest.raises(DispatchAlreadyCommitted):
                with registered_generator(c.spec, c.op, **dependencies):
                    pytest.fail("duplicate resource")
            assert len(commands) == before
            assert authorities.actual.closed == closed
            assert (
                engine.capture.termination is not None
                and engine.capture.termination.returncode == 0
            )
            result = {
                "passed": True,
                "job_id": os.environ["SLURM_JOB_ID"],
                "software_receipt": str(receipt),
                "worker": closed.target.worker.writer.model_dump(mode="json"),
                "owner_guard": acquired["owner_guard"],
                "execution_authority": type(runtime_authority).__name__,
                "execution_record": execution.model_dump(mode="json"),
                "closed_resource_replay_additional_commands": 0,
                "fixture_inference_authority_called": False,
                "resource_authority": type(authorities.actual).__name__,
                "resource_authority_scope": "engineering",
                "resource_authority_observations": [
                    r.model_dump(mode="json") for r in authorities.actual.observations
                ],
                "run_binding": admission.run.model_dump(mode="json"),
                "lower_fixture_called": bool(c.authority.workers or c.authority.closed),
                "states": [e.state for e in record.events],
                "output": first.model_dump(mode="json"),
                "generation_wire_commands": count,
                "completed_replay_additional_commands": 0,
                "resource_replay_additional_commands": 0,
                "model_inventory_sha256": inventory_sha,
                "frozen_model": artifact.model_dump(mode="json"),
                "release_ref": release_ref.model_dump(mode="json"),
                "model_binding_ref": model_ref.model_dump(mode="json"),
                "resource_spec_version": c.spec.schema_version,
                "installed_sources": (
                    engine.installed_sources.model_dump(mode="json")
                    if engine.installed_sources is not None
                    else None
                ),
                "record": record.model_dump(mode="json"),
                "step_started": started.model_dump(mode="json"),
                "step_closed": closed.model_dump(mode="json"),
                "launcher_termination": ending["termination"],
                "production_authority": False,
                "formal_experiments_run": False,
            }
        except BaseException as error:
            capture = engine.capture if engine is not None else retained_capture(error)
            if capture is not None:
                raise record_failure(output, "operation", error, capture)
            raise
    assert not staged.parent.exists()
    result["local_staging_removed_after_step_closure"] = True
    verify_source(receipt)
    (output / "actual-resource-result.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
