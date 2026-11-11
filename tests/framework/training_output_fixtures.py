"""Real complete files, explicitly synthetic native-format and worker facts.

No real parameter training, formal source grant, installed/GPU authority or
valid tensor serialization is claimed by these opaque binary fixtures.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
import hashlib
import json
import os
from uuid import uuid4
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    NativeTrainingExecution,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    ResourceOwner,
    ClosureReceipt,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.adapters.training.inputs import build_sft_inputs
from lab_generate_skill.adapters.training.native_execution import (
    publish_native_return,
    OriginalTrainingOutputAuthority,
)
from lab_generate_skill.adapters.training.output_store import SFTOutputStore
from lab_generate_skill.adapters.training.files import atomic_json
from lab_generate_skill.policies.training_metadata import training_metadata
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_control_fixtures import EvidenceFixtureStore
from construction_storage_fixtures import put
from training_entry_fixtures import TrainingCase


class RecordingOutputStore(EvidenceFixtureStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.put_sizes: list[int] = []

    def put(
        self,
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        self.put_sizes.append(len(data))
        return super().put(data, metadata, control, exchange_id=exchange_id)


class UnitNativeWorkerAuthority:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.denied = False
        self.calls: list[str] = []

    def verify_capture(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        token: AllocationToken,
        worker: ProcessIdentity,
        installation_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Unit original worker/output rights denied")
        assert plan.workspace_root == str(
            self.workspace
        ) and plan.training.training_id.startswith("unit-sft-")
        assert (
            worker.node_id == "unit-node-not-actual-GPU"
            and token.resource_kind == "trainer_model"
        )
        self.calls.append("capture")

    def verify_return(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        control: OperationControl,
    ) -> None:
        self.verify_capture(
            plan, data, native.token, native.worker, native.installation_ref, control
        )
        self.calls.append("returned")

    def verify_closed(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        closure: ClosureReceipt,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> None:
        self.verify_capture(
            plan, data, native.token, native.worker, native.installation_ref, control
        )
        assert closure.token == native.token and closure.status == "closed"
        self.calls.append("closed-" + phase)


def write_native_format(
    plan: TrainingOutputPlan,
    data: LoadedDataset,
    *,
    completed: bool = True,
    step: int = 1,
    total: int = 1,
    large_bytes: int = 0,
) -> None:
    output = Path(plan.output_root)
    output.mkdir(mode=0o700)
    request = build_sft_inputs(plan.training, data, output)
    atomic_json(output / "run_manifest.json", request.contract)
    config = {
        **vars(request.args),
        "output_dir": str(output),
        "train_data": str(request.args.train_data),
        "dev_data": str(request.args.dev_data),
        "train_rows": 1,
        "dev_rows": 1,
        "trainable_parameters": 5,
        "total_parameters": 100,
        "planned_optimizer_steps": total,
        "optimizer_steps_for_all_epochs": 3,
        "warmup_steps": 0,
        "dtype": "bfloat16",
        "attention_implementation": "sdpa",
        "assistant_loss_mask": "prompt prefix labels are -100",
    }
    atomic_json(output / "training_config.json", config)
    checkpoint = output / f"checkpoint-{step:06d}"
    atomic_json(checkpoint / "complete.json", {"complete": True, "step": step})
    atomic_json(
        checkpoint / "adapter/adapter_config.json",
        {"unit_opaque_fixture_not_a_real_adapter": True},
    )
    (checkpoint / "adapter/adapter_model.safetensors").write_bytes(
        b"unit opaque fixture; not actual model weights"
    )
    with (checkpoint / "training_state.pt").open("wb") as stream:
        left = large_bytes
        while left:
            chunk = b"U" * min(left, 1024 * 1024)
            stream.write(chunk)
            left -= len(chunk)
        stream.write(b"unit-original-tail")
    atomic_json(
        output / "tokenizer/tokenizer_config.json", {"unit_no_real_tokenizer": True}
    )
    (output / "tokenizer/tokenizer.json").write_text('{"unit":true}')
    (output / "metrics.jsonl").write_text('{"unit_synthetic_metric":true}\n')
    if completed:
        atomic_json(
            output / "final_adapter/adapter_config.json", {"unit_opaque_fixture": True}
        )
        (output / "final_adapter/adapter_model.safetensors").write_bytes(
            b"unit final opaque fixture"
        )
        atomic_json(
            output / "training_summary.json",
            dict(
                complete=True,
                global_step=step,
                planned_optimizer_steps=total,
                epochs_visited=1,
                max_steps_limited=True,
                checkpoint_selection="unit original-format fixture only",
                epoch_eval_metrics=[
                    dict(step=0, epoch=0, loss=1.0, evaluation_kind="initial")
                ],
                initial_eval_loss=1.0,
                invocation_initial_eval_loss=1.0,
                final_eval_loss=0.5,
                elapsed_seconds=1.0,
                elapsed_seconds_scope="unit timing",
                checkpoint_lineage_elapsed_seconds=1.0,
                checkpoint_lineage_elapsed_scope="unit timing",
                resumed_from_checkpoint=None,
                peak_memory_gib=0.0,
                train_rows=1,
                dev_rows=1,
                max_seq_length=16384,
                adapter="final_adapter",
            ),
        )


@dataclass
class OutputCase:
    source: TrainingCase
    workspace: Path
    plan: TrainingOutputPlan
    store: RecordingOutputStore
    worker_authority: UnitNativeWorkerAuthority
    token: AllocationToken
    worker: ProcessIdentity
    installation_ref: EvidenceRef
    closure: ClosureReceipt

    @property
    def data(self) -> LoadedDataset:
        return self.source.data

    def control(self) -> OperationControl:
        return self.source.export.deps.controls.bind(
            self.plan.training.dataset.operation
        )

    def returned(self) -> EvidenceRef:
        return publish_native_return(
            self.plan,
            self.data,
            self.token,
            self.worker,
            self.installation_ref,
            self.store,
            self.worker_authority,
            self.control(),
        )

    def checkpoints(self) -> SFTOutputStore:
        return SFTOutputStore(
            self.workspace,
            self.store,
            OriginalTrainingOutputAuthority(self.store, self.worker_authority),
        )


def output_case(
    c: TrainingCase,
    name: str,
    *,
    completed: bool = True,
    large_bytes: int = 0,
    create_files: bool = True,
) -> OutputCase:
    training = c.plan("output-" + name + "-" + uuid4().hex)
    if not completed:
        training = TrainingPlan.model_validate(
            {
                **training.model_dump(),
                "spec": training.spec.model_copy(update={"max_steps": 2}),
            }
        )
    workspace = c.root / ("output-" + uuid4().hex)
    workspace.mkdir(mode=0o700)
    publication = workspace / "published"
    publication.mkdir(mode=0o700)
    evidence = workspace / "evidence"
    evidence.mkdir(mode=0o700)
    store = RecordingOutputStore(evidence)
    store.put(training.model_dump_json().encode(), training_metadata("training-plan/1"))
    output = workspace / (
        "sft-" + hashlib.sha256(training.training_id.encode()).hexdigest()
    )
    plan = TrainingOutputPlan(
        training=training,
        workspace_root=str(workspace),
        output_root=str(output),
        publication_root=str(publication),
        max_files=128,
        max_file_bytes=128 * 1024**2,
        max_total_bytes=512 * 1024**2,
    )
    owner = ResourceOwner(
        run_id=training.dataset.operation.run_id,
        owner_id=training.dataset.operation.owner_id,
        job_id="unit-job-no-training",
        worker_id="unit-trainer",
    )
    token = AllocationToken(
        allocation_id="unit-" + uuid4().hex,
        owner=owner,
        scope="batch",
        resource_kind="trainer_model",
        expected_resource_id="unit-trainer",
        provider_id="unit-no-GPU-provider",
        provider_version="1",
        recovery_ref=put(
            store, {"unit": "no real recovery permission"}, "recovery-plan/1"
        ),
    )
    worker = ProcessIdentity(
        node_id="unit-node-not-actual-GPU",
        boot_id="unit-boot",
        process_id=os.getpid(),
        start_ticks=1,
    )
    install = put(
        store, {"unit": "no real installation permission"}, "release-installation/1"
    )
    closed = put(
        store, {"unit": "no real Slurm closure proof"}, "unit-original-closure/1"
    )
    closure = ClosureReceipt(
        token=token, operation_id="unit-closed", status="closed", evidence=(closed,)
    )
    if create_files:
        write_native_format(
            plan,
            c.data,
            completed=completed,
            total=1 if completed else 2,
            large_bytes=large_bytes,
        )
    return OutputCase(
        c,
        workspace,
        plan,
        store,
        UnitNativeWorkerAuthority(workspace),
        token,
        worker,
        install,
        closure,
    )
