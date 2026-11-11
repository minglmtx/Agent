"""Explicit synthetic source/model/step fixtures, never a formal SFT grant."""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree
from lab_generate_skill.adapters.slurm.step_launch import training_step_name
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.training.worker_backend import FixedTrainingBackend
from lab_generate_skill.adapters.training.worker_service import TrainingWorkerService
from lab_generate_skill.adapters.training.resource import RegisteredTrainingResource
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)
from lab_generate_skill.adapters.training import (
    resource as resource_module,
    resource_steps as steps,
)
from lab_generate_skill.adapters.training.resource_records import metadata, put_raw
from lab_generate_skill.bootstrap.training_resource import registered_training_runtime
from lab_generate_skill.domain.training_resource import (
    TrainingResourceSpec,
    TrainingSlurmBinding,
    TrainingLaunch,
    TrainingResourceAcquired,
    TrainingStepStarted,
    TrainingStepClosed,
    TrainingStepCleanup,
)
from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.training_output import NativeTrainingExecution
from lab_generate_skill.domain.release import (
    ReleaseArtifact,
    ReleaseFile,
    ReleaseManifest,
)
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.slurm_allocation import (
    SlurmAllocationObservation,
    SlurmCgroupMembership,
)
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.slurm_quiescence import SlurmUserRemoval
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    ClosureReceipt,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.policies.training_metadata import training_metadata
from training_worker_fixtures import WorkerCase, worker_case, UnitChannel
from training_worker_install_fixtures import prepared_unit_source
from training_entry_fixtures import UnitTrainingAuthority
from training_output_fixtures import write_native_format
from actor_installation_fixtures import declaration, unit_verifier
from generator_release_fixtures import metadata as release_metadata
from actor_worker_fixtures import unit_guard
from allocation_fixtures import Case as AllocationCase
from test_slurm_probe import operation as allocation_operation
from test_resource_journal import NoCancellation


class UnitAllocation(SlurmAllocationVerifier):
    def __init__(self, original: SlurmAllocationObservation) -> None:
        self.original = original

    def observe(
        self,
        execution: SlurmExecutionIdentity,
        writer: ProcessIdentity,
        op: OperationContext,
    ) -> SlurmAllocationObservation:
        assert (
            execution == self.original.facts.execution
            and writer == self.original.facts.writer
        )
        return self.original


class UnitResourceAuthority:
    def __init__(self) -> None:
        self.denied: str | None = None
        self.calls: list[str] = []

    def _check(self, phase: str, control: OperationControl) -> None:
        control.checkpoint()
        self.calls.append(phase)
        if self.denied == phase:
            raise PermissionError("Unit training resource " + phase + " denied")

    def authorize_start(
        self, spec: TrainingResourceSpec, control: OperationControl
    ) -> None:
        self._check("start", control)
        assert spec.configuration.output.training.training_id.startswith("unit-sft-")

    def authorize_training(
        self, launch: TrainingLaunch, data: LoadedDataset, control: OperationControl
    ) -> None:
        self._check("training", control)
        assert all(e.task.family == "unit-contract-only" for e in data.examples)

    def verify_started(
        self,
        spec: TrainingResourceSpec,
        acquired: TrainingResourceAcquired,
        control: OperationControl,
    ) -> None:
        self._check("started", control)
        assert acquired.step.allocation == spec.slurm.allocation

    def verify_closed(
        self,
        spec: TrainingResourceSpec,
        handle: TrainingStepCleanup,
        termination: ProcessTermination,
        observed: TrainingStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._check("closed", control)
        assert (
            not handle.start_attempted and termination.state == "not_started"
        ) or observed is not None

    def authorize_read(
        self,
        spec: TrainingResourceSpec,
        native: NativeTrainingExecution,
        closure: ClosureReceipt,
        phase: str,
        control: OperationControl,
    ) -> None:
        self._check("read", control)
        assert native.token == closure.token == spec.configuration.token


@dataclass
class TrainingResourceCase:
    c: WorkerCase
    spec: TrainingResourceSpec
    journal: FileResourceJournal
    controls: OperationGuards
    clock: SystemClock
    source_authority: UnitTrainingAuthority
    authority: UnitResourceAuthority
    allocator: SlurmAllocationVerifier
    channels: list["UnitOwnedChannel"]
    cores: list[dict[str, Any]]

    def runtime(self) -> RecordedTrainingRuntime:
        return registered_training_runtime(
            self.spec,
            journal=self.journal,
            evidence=self.c.store,
            controls=self.controls,
            clock=self.clock,
            source_authority=self.source_authority,
            resource_authority=self.authority,
            allocation_verifier=self.allocator,
        )


def resource_case(
    root: Path,
    allocation: SlurmAllocationObservation,
    installation: ReleaseInstallation | None = None,
) -> TrainingResourceCase:
    c = worker_case(prepared_unit_source(), root, installation)
    cfg = c.configuration
    model_root = root / "unit-model-no-real-tensors"
    model_root.mkdir()
    entries = []
    for name in [
        "config.json",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "model.safetensors",
    ]:
        raw = b"unit-not-real-tensors" if name == "model.safetensors" else b"{}"
        (model_root / name).write_bytes(raw)
        (model_root / name).chmod(0o444)
        entries.append(
            ReleaseFile(
                path=name,
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                executable=False,
            )
        )
    model_root.chmod(0o555)
    model = ReleaseArtifact(
        artifact_id="unit-sft-base-not-real-model",
        root=str(model_root),
        files=tuple(sorted(entries, key=lambda e: e.path)),
    )
    base = cfg.installation.manifest
    gen = next(
        r.component_id
        for r in base.roles
        if (r.role, r.scope_id) == ("generator", "global")
    )
    components = tuple(
        (
            v.model_copy(
                update={
                    "artifact_ids": (model.artifact_id,),
                    "interface_id": "local-generator-engine",
                    "contract_version": "1.0",
                }
            )
            if v.component_id == gen
            else v
        )
        for v in base.components
    )
    manifest = ReleaseManifest.model_validate(
        {
            **base.model_dump(),
            "artifacts": (*base.artifacts, model),
            "components": components,
        }
    )
    install = declaration(
        manifest,
        Path(cfg.installation.workspace_root),
        Path(cfg.installation.python_executable),
    )
    install_ref = c.store.put(
        install.model_dump_json().encode(), metadata("release-installation/1")
    )
    # Same bytes/reference producer as the one original installation recipe.
    assert (
        c.store.put(
            manifest.model_dump_json().encode(), release_metadata("release-manifest/1")
        )
        == install.manifest_ref
    )
    training = TrainingPlan.model_validate(
        {
            **cfg.output.training.model_dump(),
            "training_release_ref": install.manifest_ref,
            "model": model,
        }
    )
    c.store.put(
        training.model_dump_json().encode(), training_metadata("training-plan/1")
    )
    owner = cfg.token.owner.model_copy(
        update={"job_id": allocation.facts.execution.job_id}
    )
    baseline = c.store.put(
        b"explicit unit no real training recovery", metadata("unit-sft-recovery/1")
    )
    recovery = RecoveryPlan(
        recovery_id="unit-sft-recovery",
        owner=owner,
        baseline_ref=baseline,
        restore_component_id="unit-sft-original-checkpoints",
        restore_component_version="1",
        state_coverage=("original_output",),
    )
    recovery_ref = c.store.put(
        recovery.model_dump_json().encode(), metadata("recovery-plan/1")
    )
    token = cfg.token.model_copy(update={"owner": owner, "recovery_ref": recovery_ref})
    output = cfg.output.model_copy(update={"training": training})
    configuration = TrainingWorkerConfiguration.model_validate(
        {
            **cfg.model_dump(),
            "output": output,
            "token": token,
            "installation": install,
            "installation_ref": install_ref,
        }
    )
    c.configuration = configuration
    op = training.dataset.operation.model_copy(
        update={
            "operation_id": "unit-sft-acquire",
            "allocation_id": token.allocation_id,
            "recovery_ref": recovery_ref,
        }
    )
    spec = TrainingResourceSpec(
        configuration=configuration,
        slurm=TrainingSlurmBinding(
            allocation=allocation,
            srun_executable="/usr/bin/srun",
            scontrol_executable="/usr/bin/scontrol",
        ),
        operation=op,
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    journal_root = root / "journal"
    journal_root.mkdir(mode=0o700)
    journal = FileResourceJournal(journal_root, owner, controls, c.store)
    return TrainingResourceCase(
        c,
        spec,
        journal,
        controls,
        clock,
        UnitTrainingAuthority(),
        UnitResourceAuthority(),
        UnitAllocation(allocation),
        [],
        [],
    )


class UnitOwnedChannel(UnitChannel):
    def __init__(
        self, service: TrainingWorkerService, case: TrainingResourceCase
    ) -> None:
        super().__init__(service)
        self.case, self.starts = case, 0
        self.process_id: int | None = None
        self.start_failure: str | None = None

    def start(self, control: OperationControl) -> None:
        control.checkpoint()
        self.starts += 1
        if self.start_failure == "before":
            raise OSError("Unit original start unknown before process")
        self.process_id = current_process_identity().process_id + 20000000
        if self.start_failure == "after":
            raise OSError("Unit original start unknown after process")

    def finish(self, control: OperationControl) -> ProcessTermination:
        control.checkpoint()
        assert self.service.closed and self.process_id is not None
        result = ProcessTermination(self.process_id, "reaped", 0, False)
        self.capture = CommandCapture(
            ("/unit-no-real-srun",), 0, b"", b"", True, result
        )
        return result

    def abort(self, control: OperationControl) -> ProcessTermination:
        control.checkpoint()
        self.aborts += 1
        self.service.close()
        result = (
            ProcessTermination(None, "not_started", None, False)
            if self.process_id is None
            else ProcessTermination(self.process_id, "reaped", -9, True)
        )
        self.capture = CommandCapture(
            ("/unit-no-real-srun",), result.returncode, b"", b"", False, result
        )
        return result


def unit_case(root: Path, patch: pytest.MonkeyPatch) -> TrainingResourceCase:
    alloc_root = root / "allocation"
    alloc_root.mkdir(parents=True)
    ac = AllocationCase(alloc_root, patch)
    observed = ac.verifier().observe(ac.execution, ac.writer, allocation_operation())
    raw = observed.model_dump()
    writer = current_process_identity()
    raw["facts"]["writer"] = writer
    raw["facts"]["cgroup"]["writer"] = writer
    raw["facts"]["controller"]["node_id"] = writer.node_id
    allocation = SlurmAllocationObservation.model_validate(raw)
    c = resource_case(root / "resource", allocation)
    backends: list[FixedTrainingBackend] = []

    def factory(
        configuration: TrainingWorkerConfiguration, guard: ProcessOwnerGuard
    ) -> FixedTrainingBackend:
        result = FixedTrainingBackend(configuration, guard, -1)
        backends.append(result)
        return result

    def channel(*args: Any, **kwargs: Any) -> UnitOwnedChannel:
        service = TrainingWorkerService(factory, unit_verifier, unit_guard)
        result = UnitOwnedChannel(service, c)
        c.channels.append(result)
        return result

    def guard_check(
        controller: ProcessIdentity,
        supervisor: ProcessIdentity,
        fd: int,
        control: OperationControl,
    ) -> ProcessOwnerGuard:
        control.checkpoint()
        return backends[-1].guard

    def core(
        args: argparse.Namespace,
        train: list[dict[str, Any]],
        dev: list[dict[str, Any]],
        contract: dict[str, Any],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert len(train) == len(dev) == 1
        c.cores.append(contract)
        write_native_format(c.spec.configuration.output, c.c.source.data)

    def started(
        spec: TrainingResourceSpec,
        observed: SlurmAllocationObservation,
        state: steps.TrainingStepState,
        worker: ProcessIdentity,
        evidence: Any,
        control: OperationControl,
    ) -> TrainingStepStarted:
        assert state.launcher is not None
        membership = observed.facts.cgroup.model_copy(
            update={
                "step_id": "0",
                "writer": worker,
                "user_path": observed.facts.cgroup.user_path.replace(
                    "step_batch", "step_0"
                ),
                "user_inode": 200,
                "task_inode": 201,
            }
        )
        state.target = SlurmStepTarget(
            execution=observed.facts.execution,
            step_name=training_step_name(spec.configuration.token),
            resources="single_gpu",
            launcher=state.launcher,
            worker=membership,
        )
        raw = json.dumps(
            dict(
                schema_version="sft-step-raw/1",
                target=state.target.model_dump(mode="json"),
                phase="started",
                error=None,
                kernel=[{"explicit_unit_not_real_kernel": True}],
                commands=[{"explicit_unit_no_srun": True}],
            ),
            sort_keys=True,
        ).encode()
        ref = put_raw(c.c.store, raw, "sft-step-raw/1", control)
        state.started = TrainingStepStarted(
            allocation=observed,
            controller=SlurmControllerStep(
                target=state.target,
                started_at_epoch=observed.facts.execution.started_at_epoch,
                gpu_type=observed.facts.controller.gpu_type,
                memory="1G",
            ),
            evidence=ref,
        )
        return state.started

    def closed(
        spec: TrainingResourceSpec,
        state: steps.TrainingStepState,
        term: ProcessTermination,
        evidence: Any,
        control: OperationControl,
        pinned: Any,
    ) -> TrainingStepClosed | None:
        if not state.start_attempted and term.state == "not_started":
            return None
        if state.target is None or term.state != "reaped":
            raise OSError("Unit original tree unconfirmed")
        raw = json.dumps(
            dict(
                schema_version="sft-step-raw/1",
                target=state.target.model_dump(mode="json"),
                phase="closed",
                error=None,
                kernel=[{"explicit_unit_not_real_kernel": True}],
                commands=[{"explicit_unit_no_srun": True}],
            ),
            sort_keys=True,
        ).encode()
        ref = put_raw(c.c.store, raw, "sft-step-raw/1", control)
        return TrainingStepClosed(
            target=state.target,
            quiescence=SlurmUserRemoval(
                original=state.target.worker, observer=writer, writer_status="missing"
            ),
            evidence=ref,
        )

    class UnitPin:
        def close(self) -> None:
            pass

    patch.setattr(resource_module, "FramedProcessSession", channel)
    patch.setattr(
        resource_module, "pin_user_tree", lambda *args: cast(PinnedUserTree, UnitPin())
    )
    patch.setattr(
        steps,
        "launcher_identity",
        lambda pid, uid, control: writer.model_copy(
            update={"process_id": pid, "start_ticks": 1}
        ),
    )
    patch.setattr(steps, "observe_started", started)
    patch.setattr(steps, "observe_closed", closed)
    patch.setattr(
        "lab_generate_skill.adapters.training.worker_backend.observed_guard",
        guard_check,
    )
    patch.setattr(
        "lab_generate_skill.adapters.training.torch_sft.run_original_sft", core
    )
    return c
