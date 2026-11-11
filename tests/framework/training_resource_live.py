"""Actual registered installed GPU-step configure/close; parameter training denied."""

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.probe import AccountingSlurmProbe
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.training.resource import RegisteredTrainingResource
from lab_generate_skill.adapters.training.resource_records import metadata, phase
from lab_generate_skill.adapters.training.inputs import build_sft_inputs
from lab_generate_skill.adapters.training.resource_steps import same_allocation
from lab_generate_skill.domain.training_resource import (
    TrainingLaunch,
    TrainingResourceSpec,
    TrainingResourceAcquired,
    TrainingStepCleanup,
    TrainingStepClosed,
)
from lab_generate_skill.domain.training_worker_call import TrainingWorkerCommand
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    RevisionConflict,
    OwnershipConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_resource_journal import NoCancellation
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard
from evidence_control_fixtures import EvidenceFixtureStore
from training_resource_fixtures import resource_case, UnitResourceAuthority
from actor_installation_fixtures import installed_declaration
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
import hashlib


class EngineeringWorkerOnlyAuthority(UnitResourceAuthority):
    def authorize_start(
        self, spec: TrainingResourceSpec, control: OperationControl
    ) -> None:
        super().authorize_start(spec, control)
        assert spec.configuration.token.owner.job_id == os.environ["SLURM_JOB_ID"]
        assert spec.slurm.allocation.facts.writer == current_process_identity()
        assert (
            spec.configuration.output.training.model.artifact_id
            == "unit-sft-base-not-real-model"
        )

    def authorize_training(
        self, launch: TrainingLaunch, data: LoadedDataset, control: OperationControl
    ) -> None:
        raise PermissionError(
            "Engineering worker-only check has no parameter training rights"
        )

    def verify_started(
        self,
        spec: TrainingResourceSpec,
        acquired: TrainingResourceAcquired,
        control: OperationControl,
    ) -> None:
        self._check("started", control)
        same_allocation(spec.slurm.allocation, acquired.step.allocation)
        assert (
            acquired.step.allocation.facts.observed_at
            >= spec.slurm.allocation.facts.observed_at
        )
        assert acquired.step.allocation.evidence != spec.slurm.allocation.evidence
        assert acquired.guard.controller == current_process_identity()
        assert acquired.guard.worker == acquired.step.controller.target.worker.writer
        assert (
            acquired.installed.manifest_sha256
            == spec.configuration.installation.manifest_ref.sha256
        )

    def verify_closed(
        self,
        spec: TrainingResourceSpec,
        handle: TrainingStepCleanup,
        termination: ProcessTermination,
        observed: TrainingStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        super().verify_closed(spec, handle, termination, observed, operation, control)
        assert observed is not None and handle.target == observed.target
        assert observed.quiescence.writer_status in ("missing", "reused")
        assert (
            termination.state == "reaped"
            and termination.process_id == observed.target.launcher.process_id
        )


def test_actual_registered_training_worker_full_step_close_without_training(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    observation_root = tmp_path / "allocation-evidence"
    observation_root.mkdir(mode=0o700)
    original_store = EvidenceFixtureStore(observation_root)
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    runner = SlurmCommandRunner()
    probe = AccountingSlurmProbe(
        original_store,
        controls,
        clock,
        runner,
        sacct=Path("/usr/bin/sacct"),
        squeue=Path("/usr/bin/squeue"),
    )
    allocator = SlurmAllocationVerifier(
        original_store,
        controls,
        clock,
        probe,
        runner,
        scontrol=Path("/usr/bin/scontrol"),
        nvidia_smi=Path("/usr/bin/nvidia-smi"),
    )
    identity, _ = actual_slurm_execution()
    pin_op = OperationContext(
        operation_id="unit-sft-live-allocation",
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    allocation = allocator.observe(identity, current_process_identity(), pin_op)
    root = installed_sources.workspace / "unit-sft-registered-resource"
    c = resource_case(root, allocation, installed_declaration(installed_sources))
    for ref in [
        allocation.evidence,
        allocation.facts.accounting_before.evidence,
        allocation.facts.accounting_after.evidence,
    ]:
        raw = original_store.read(ref)
        meta = EvidenceMetadata(
            media_type=ref.media_type,
            content_schema=ref.content_schema,
            visibility=ref.visibility,
            producer=ref.producer,
        )
        assert c.c.store.put(raw, meta) == ref
    actual_probe = AccountingSlurmProbe(
        c.c.store,
        c.controls,
        c.clock,
        runner,
        sacct=Path("/usr/bin/sacct"),
        squeue=Path("/usr/bin/squeue"),
    )
    c.allocator = SlurmAllocationVerifier(
        c.c.store,
        c.controls,
        c.clock,
        actual_probe,
        runner,
        scontrol=Path("/usr/bin/scontrol"),
        nvidia_smi=Path("/usr/bin/nvidia-smi"),
    )
    authority = EngineeringWorkerOnlyAuthority()
    contract = build_sft_inputs(
        c.spec.configuration.output.training,
        c.c.source.data,
        Path(c.spec.configuration.output.output_root),
    ).contract
    command = TrainingWorkerCommand(
        session_id=c.spec.configuration.token.expected_resource_id,
        sequence=2,
        operation="train",
        remaining_seconds=120.0,
        contract_sha256=hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
    )
    launch = TrainingLaunch(
        spec=c.spec,
        train=command,
        command_ref=evidence_reference(
            command.model_dump_json().encode(), metadata("sft-worker-command/1")
        ),
    )
    resource = RegisteredTrainingResource(
        launch,
        journal=c.journal,
        evidence=c.c.store,
        controls=c.controls,
        clock=c.clock,
        authority=authority,
        allocation_verifier=c.allocator,
    )
    try:
        resource.start(guard(120))
        assert resource.worker is not None and resource.worker.guard is not None
        assert resource.state == "acquired"
        closure = resource.close(guard(60))
        assert (
            closure.status == "closed"
            and closure.primary_error is None
            and not closure.cleanup_errors
        )
        assert resource.close(guard()) == closure
        assert [e.decoded.operation for e in resource.worker.exchanges] == [
            "configure",
            "close",
        ]
        assert not Path(c.spec.configuration.output.output_root).exists()
        record = c.journal.read(
            c.spec.configuration.token,
            c.spec.operation.cleanup(
                "unit-live-closed-read", now=c.clock.utcnow(), seconds=30
            ),
        )
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        ending = (
            json.loads(c.c.store.read(resource.ending_ref))
            if resource.ending_ref is not None
            else {}
        )
        assert ending["step"]["quiescence"]["writer_status"] in ("missing", "reused")
        repeat = RegisteredTrainingResource(
            launch,
            journal=c.journal,
            evidence=c.c.store,
            controls=c.controls,
            clock=c.clock,
            authority=authority,
            allocation_verifier=c.allocator,
        )
        with pytest.raises(
            (DispatchAlreadyCommitted, RevisionConflict, OwnershipConflict)
        ):
            repeat.start(guard(30))
        output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        (output / "sft-registered-resource-native.json").write_text(
            json.dumps(
                dict(
                    actual_installed_worker=True,
                    actual_original_slurm_gpu_step=True,
                    actual_whole_step_closed=True,
                    parameter_training_or_model_calls=0,
                    formal_source_or_phase_authority=False,
                    known_original_journal_closed=True,
                    repeat_start_denied=True,
                    closure=closure.model_dump(mode="json"),
                    resource_record=record.model_dump(mode="json"),
                    scope="engineering worker-only, no tensors/tokenizer/GPU inference or parameter training",
                ),
                indent=2,
            )
            + "\n"
        )
    finally:
        if resource.owned and resource.closure is None and resource.close_error is None:
            resource.close(guard(60))
