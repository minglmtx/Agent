"""Synthetic SFT wire/rows only. No actual phase, GPU, weights or training grant."""

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Protocol
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.training_output import TrainingOutputPlan
from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration
from lab_generate_skill.domain.lifecycle import AllocationToken, ResourceOwner
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.adapters.training.inputs import build_sft_inputs
from lab_generate_skill.adapters.training.worker_service import TrainingWorkerService
from lab_generate_skill.adapters.training.worker_protocol import decode_command
from lab_generate_skill.domain.training_worker_call import TrainingWorkerCommand
from lab_generate_skill.adapters.training.worker_client import SupervisedTrainingWorker
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.training_metadata import training_metadata
from lab_generate_skill.policies.dataset_manifest import export_metadata
from actor_installation_fixtures import unit_declaration, unit_verifier
from actor_worker_fixtures import unit_guard
from evidence_control_fixtures import EvidenceFixtureStore
from training_entry_fixtures import ref


class WorkerFixtureSource(Protocol):
    @property
    def data(self) -> LoadedDataset: ...
    def plan(self, name: str) -> TrainingPlan: ...


@dataclass
class WorkerCase:
    source: WorkerFixtureSource
    configuration: TrainingWorkerConfiguration
    store: EvidenceFixtureStore

    @property
    def digest(self) -> str:
        c = self.configuration
        contract = build_sft_inputs(
            c.output.training, self.source.data, Path(c.output.output_root)
        ).contract
        return hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()


def worker_case(
    source: WorkerFixtureSource,
    root: Path,
    installation: ReleaseInstallation | None = None,
) -> WorkerCase:
    root.mkdir(mode=0o700, parents=True)
    installation = installation or ReleaseInstallation.model_validate(
        {**unit_declaration().model_dump(), "workspace_root": str(root)}
    )
    training = TrainingPlan.model_validate(
        {
            **source.plan("worker-" + root.name).model_dump(),
            "training_release_ref": installation.manifest_ref,
        }
    )
    output = TrainingOutputPlan(
        training=training,
        workspace_root=installation.workspace_root,
        output_root=str(
            root / ("sft-" + hashlib.sha256(training.training_id.encode()).hexdigest())
        ),
        publication_root=str(root / "published"),
        max_files=128,
        max_file_bytes=1024**2,
        max_total_bytes=16 * 1024**2,
    )
    (root / "evidence").mkdir(mode=0o700)
    (root / "published").mkdir(mode=0o700)
    store = EvidenceFixtureStore(root / "evidence")
    owner = ResourceOwner(
        run_id=training.dataset.operation.run_id,
        owner_id=training.dataset.operation.owner_id,
        job_id="unit-job",
        worker_id="unit-worker",
    )
    token = AllocationToken(
        allocation_id="unit-trainer",
        owner=owner,
        scope="batch",
        resource_kind="trainer_model",
        expected_resource_id="unit-trainer",
        provider_id="fixed-sft-worker",
        provider_version="1",
        recovery_ref=ref("unit-recovery", "recovery-plan/1"),
    )
    installation_ref = store.put(
        installation.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="release-installation/1",
            visibility="private",
            producer="unit-sft-worker",
        ),
    )
    store.put(training.model_dump_json().encode(), training_metadata("training-plan/1"))
    data = source.data
    assert data.manifest is not None
    store.put(
        data.receipt.model_dump_json().encode(), export_metadata("export-receipt/1")
    )
    store.put(
        data.manifest.model_dump_json().encode(), export_metadata("dataset-manifest/1")
    )
    for e in data.examples:
        store.put(e.model_dump_json().encode(), export_metadata("training-example/1"))
    return WorkerCase(
        source,
        TrainingWorkerConfiguration(
            output=output,
            token=token,
            installation=installation,
            installation_ref=installation_ref,
            evidence_root=str(root / "evidence"),
        ),
        store,
    )


class UnitBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.closes = 0
        self.error: BaseException | None = None
        self.cleanup: BaseException | None = None
        self.reference = ref("unit-native-not-real-training", "sft-native-execution/1")

    def execute(self, digest: str, control: OperationControl) -> EvidenceRef:
        control.checkpoint()
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.reference

    def close(self, control: OperationControl) -> None:
        control.checkpoint()
        self.closes += 1
        if self.cleanup is not None:
            raise self.cleanup


class UnitChannel:
    def __init__(self, service: TrainingWorkerService) -> None:
        self.service = service
        self.sent: list[bytes] = []
        self.lose_reply = False
        self.abort_error: BaseException | None = None
        self.aborts = 0
        self.capture = CommandCapture(("/unit-sft-worker",), None, b"", b"", False)

    def exchange(self, payload: bytes, control: OperationControl) -> bytes:
        control.checkpoint()
        self.sent.append(payload)
        reply = self.service.handle(decode_command(payload)).model_dump_json().encode()
        if self.lose_reply:
            raise TimeoutError("Unit reply lost after backend returned")
        return reply

    def finish(self, control: OperationControl) -> ProcessTermination:
        control.checkpoint()
        assert self.service.closed
        return ProcessTermination(1, "reaped", 0, False)

    def abort(self, control: OperationControl) -> ProcessTermination:
        control.checkpoint()
        self.aborts += 1
        self.service.close()
        if self.abort_error is not None:
            raise self.abort_error
        return ProcessTermination(1, "reaped", -9, True)


def unit_client(
    c: WorkerCase,
) -> tuple[UnitBackend, TrainingWorkerService, UnitChannel, SupervisedTrainingWorker]:
    backend = UnitBackend()
    service = TrainingWorkerService(
        lambda configuration, guard: backend, unit_verifier, unit_guard
    )
    channel = UnitChannel(service)
    return (
        backend,
        service,
        channel,
        SupervisedTrainingWorker(channel, "unit-session", c.configuration),
    )


def train_command(
    c: WorkerCase,
    client: SupervisedTrainingWorker,
    *,
    digest: str | None = None,
    seconds: float = 5.0,
) -> TrainingWorkerCommand:
    return TrainingWorkerCommand(
        session_id=client.session_id,
        sequence=2,
        operation="train",
        remaining_seconds=seconds,
        contract_sha256=c.digest if digest is None else digest,
    )
