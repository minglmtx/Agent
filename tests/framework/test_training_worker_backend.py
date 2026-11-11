"""Real file/wire combination, synthetic dataset and model leaf; never real training."""

import argparse
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.training_output import (
    NativeTrainingExecution,
    output_artifact_id,
)
from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.adapters.training.worker_backend import (
    FixedTrainingBackend,
    WorkerEvidence,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.adapters.training.worker_service import TrainingWorkerService
from lab_generate_skill.adapters.training.worker_client import (
    SupervisedTrainingWorker,
    TrainingWorkerFailure,
)
from lab_generate_skill.adapters.training.native_execution import validate_native_return
from lab_generate_skill.adapters.training.native_output import native_training_outcome
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_installation_fixtures import unit_verifier
from actor_worker_fixtures import unit_guard
from training_entry_fixtures import (
    TrainingCase,
    training_case as training_case,
    ref as unit_ref,
)
from training_worker_fixtures import worker_case, UnitChannel, train_command
from training_output_fixtures import write_native_format
from test_slurm_commands import guard


@pytest.mark.parametrize("lost_ack", [False, True])
def test_original_core_return_to_native_files_and_existing_outcome_consumer(
    training_case: TrainingCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lost_ack: bool,
) -> None:
    c = worker_case(training_case, tmp_path / "unit-combination")
    backends: list[FixedTrainingBackend] = []
    core_calls: list[dict[str, Any]] = []

    def factory(
        configuration: TrainingWorkerConfiguration, owner: ProcessOwnerGuard
    ) -> FixedTrainingBackend:
        backend = FixedTrainingBackend(configuration, owner, -1)
        backends.append(backend)
        return backend

    def observed(
        controller: ProcessIdentity,
        supervisor: ProcessIdentity,
        fd: int,
        control: OperationControl,
    ) -> ProcessOwnerGuard:
        control.checkpoint()
        assert fd == -1
        return backends[0].guard

    def core(
        args: argparse.Namespace,
        train: list[dict[str, Any]],
        dev: list[dict[str, Any]],
        contract: dict[str, Any],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert args.output_dir == Path(c.configuration.output.output_root)
        assert len(train) == len(dev) == 1
        core_calls.append(contract)
        write_native_format(c.configuration.output, c.source.data)

    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.worker_backend.observed_guard", observed
    )
    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.worker_backend.verify_artifact",
        lambda artifact, control: control.checkpoint(),
    )
    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.torch_sft.run_original_sft", core
    )
    original_put = WorkerEvidence.put

    def put_then_lose_ack(
        self: WorkerEvidence,
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl,
    ) -> EvidenceRef:
        reference = original_put(self, raw, metadata, control)
        if lost_ack and metadata.content_schema == "sft-native-execution/1":
            raise TimeoutError("Unit native return committed but acknowledgement lost")
        return reference

    monkeypatch.setattr(WorkerEvidence, "put", put_then_lose_ack)
    service = TrainingWorkerService(factory, unit_verifier, unit_guard)
    client = SupervisedTrainingWorker(
        UnitChannel(service), "unit-combination", c.configuration
    )
    client.configure(guard())
    assert not Path(c.configuration.output.output_root).exists() and not core_calls
    if lost_ack:
        with pytest.raises(TrainingWorkerFailure) as error:
            client.train(train_command(c, client), guard())
        reply = error.value.exchange.decoded
        assert reply.status == "error" and reply.execution_ref is not None
        ref = reply.execution_ref
    else:
        ref = client.train(train_command(c, client), guard())
    native = NativeTrainingExecution.model_validate_json(c.store.read(ref))
    validate_native_return(c.configuration.output, c.source.data, native)
    assert client.guard is not None
    assert native.worker == client.guard.worker
    assert native.installation_ref == c.configuration.installation_ref
    if not lost_ack:
        client.close(guard())
    assert len(core_calls) == 1 and backends[0].state == "closed"
    snapshot = FileArtifactFreezer(
        Path(c.configuration.output.workspace_root),
        Path(c.configuration.output.publication_root),
    ).freeze(native.source, output_artifact_id(native.source), guard())
    outcome = native_training_outcome(
        c.configuration.output, c.source.data, snapshot, guard()
    )
    assert outcome.status == "completed" and outcome.optimizer_steps == 1
    assert c.store.read(ref) == native.model_dump_json().encode()
    with pytest.raises(OwnershipConflict, match="once-only"):
        client.train(train_command(c, client), guard())
    closure = ClosureReceipt(
        token=c.configuration.token,
        operation_id="unit-close-no-real-GPU",
        status="closed",
        evidence=(unit_ref("unit-no-real-GPU", "unit-closure/1"),),
    )
    with pytest.raises(OwnershipConflict, match="self-certify"):
        backends[0].verify_closed(
            c.configuration.output, c.source.data, native, closure, "read", guard()
        )


@pytest.mark.parametrize(
    "fault", ["missing-plan", "row-tail", "contract", "model", "missing-root"]
)
def test_original_byte_or_model_failure_precedes_core_and_never_retries(
    training_case: TrainingCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    from lab_generate_skill.domain.evidence_identity import evidence_reference
    from lab_generate_skill.policies.training_metadata import training_metadata

    c = worker_case(training_case, tmp_path / fault)
    backends: list[FixedTrainingBackend] = []
    calls: list[str] = []

    def factory(
        configuration: TrainingWorkerConfiguration, owner: ProcessOwnerGuard
    ) -> FixedTrainingBackend:
        b = FixedTrainingBackend(configuration, owner, -1)
        backends.append(b)
        return b

    def observed(
        controller: ProcessIdentity,
        supervisor: ProcessIdentity,
        fd: int,
        control: OperationControl,
    ) -> ProcessOwnerGuard:
        control.checkpoint()
        return backends[0].guard

    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.worker_backend.observed_guard", observed
    )
    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.torch_sft.run_original_sft",
        lambda *args: calls.append("core"),
    )
    blobs = Path(c.configuration.evidence_root) / "blobs"
    if fault == "missing-plan":
        ref = evidence_reference(
            c.configuration.output.training.model_dump_json().encode(),
            training_metadata("training-plan/1"),
        )
        (blobs / ref.sha256).unlink()
    elif fault == "row-tail":
        assert c.source.data.manifest is not None
        path = blobs / c.source.data.manifest.items[-1].example_ref.sha256
        path.write_bytes(path.read_bytes() + b"tail")
    elif fault == "missing-root":
        for p in blobs.iterdir():
            p.unlink()
        blobs.rmdir()
        Path(c.configuration.evidence_root).rmdir()
    service = TrainingWorkerService(factory, unit_verifier, unit_guard)
    client = SupervisedTrainingWorker(
        UnitChannel(service), "unit-refusal", c.configuration
    )
    client.configure(guard())
    with pytest.raises(TrainingWorkerFailure) as error:
        client.train(
            train_command(
                c, client, digest="0" * 64 if fault == "contract" else c.digest
            ),
            guard(),
        )
    assert error.value.exchange.decoded.error is not None
    assert not calls and backends[0].state == "closed"
    assert not Path(c.configuration.output.output_root).exists()
    with pytest.raises(OwnershipConflict, match="once-only"):
        client.train(train_command(c, client), guard())
    if fault == "missing-root":
        assert not Path(c.configuration.evidence_root).exists()
