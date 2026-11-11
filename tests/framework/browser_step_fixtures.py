"""Explicit synthetic step seams for unit tests; real mode observes the cluster."""

import pytest
from lab_generate_skill.domain.browser_step import (
    BrowserSlurmBinding,
    BrowserStepStarted,
    BrowserStepClosed,
    BrowserProcessStop,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.slurm_quiescence import SlurmUserQuiescence
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.browsergym.step import BrowserStepState
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.step_launch import browser_step_name
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from slurm_step_fixtures import target
from test_linux_cgroups import actual_slurm_execution


def binding(job_id: str, *, real: bool) -> BrowserSlurmBinding:
    parent = current_process_identity()
    if real:
        execution, _ = actual_slurm_execution()
        assert job_id == execution.job_id
        membership = observe_process_cgroup(
            execution, parent, DeadlineControl(15, "browser-fixture-parent")
        ).membership
    else:
        t = target()
        execution = t.execution.model_copy(
            update={"job_id": job_id, "raw_job_id": job_id}
        )
        membership = t.worker.model_copy(
            update={
                "job_id": job_id,
                "step_id": "batch",
                "writer": parent,
                "user_path": f"/sys/fs/cgroup/system.slice/slurmstepd.scope/job_{job_id}/step_batch/user",
            }
        )
    return BrowserSlurmBinding(
        execution=execution,
        parent=membership,
        srun_executable="/usr/bin/srun",
        scontrol_executable="/usr/bin/scontrol",
    )


def raw(store: EvidenceStore, control: OperationControl) -> EvidenceRef:
    return store.put(
        b'{"engineering_only":true}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="browser-step-raw/1",
            visibility="private",
            producer="unit-step",
        ),
        control=control,
    )


class UnitProcesses:
    """Synthetic handles only; no process signals or production permission."""

    def __init__(self, guard: ProcessOwnerGuard, target: SlurmStepTarget) -> None:
        self.facts = BrowserProcessStop(guard=guard, target=target)
        self.closed = False

    def stop(self, control: OperationControl) -> BrowserProcessStop:
        control.checkpoint()
        self.facts = self.facts.model_copy(
            update={"worker_exit_observed": True, "supervisor_exit_observed": True}
        )
        return self.facts

    def close(self) -> None:
        self.closed = True


def unit_started(
    spec: BrowserResourceSpec,
    state: BrowserStepState,
    guard: ProcessOwnerGuard,
    evidence: EvidenceStore,
    control: OperationControl,
) -> BrowserStepStarted:
    assert state.launcher is not None
    membership = spec.slurm.parent.model_copy(
        update={
            "step_id": "0",
            "writer": guard.worker,
            "user_inode": spec.slurm.parent.user_inode + 100,
            "task_inode": spec.slurm.parent.task_inode + 100,
            "user_path": spec.slurm.parent.user_path.replace("step_batch", "step_0"),
        }
    )
    state.target = SlurmStepTarget(
        execution=spec.slurm.execution,
        resources="cpu_only",
        step_name=browser_step_name(spec.token),
        launcher=state.launcher,
        worker=membership,
    )
    state.started = BrowserStepStarted(
        controller=SlurmControllerStep(
            target=state.target,
            started_at_epoch=spec.slurm.execution.started_at_epoch,
            gpu_type=None,
            memory="1M",
        ),
        evidence=raw(evidence, control),
    )
    return state.started


def unit_closed(
    spec: BrowserResourceSpec,
    state: BrowserStepState,
    termination: ProcessTermination | None,
    evidence: EvidenceStore,
    control: OperationControl,
    *,
    metadata_control: OperationControl | None = None,
) -> BrowserStepClosed | None:
    control.checkpoint()
    if state.target is None:
        if termination is not None and termination.state == "not_started":
            return None
        raise ValueError("Unit step lacks original target; retain quarantine")
    return BrowserStepClosed(
        target=state.target,
        quiescence=SlurmUserQuiescence(
            original=state.target.worker,
            observer=spec.slurm.parent.writer,
            writer_status="missing",
        ),
        evidence=raw(
            evidence, metadata_control if metadata_control is not None else control
        ),
    )


def install_unit_step(monkeypatch: pytest.MonkeyPatch) -> None:
    from lab_generate_skill.adapters.browsergym import step

    def parent(
        spec: BrowserResourceSpec,
        controller: ProcessIdentity,
        control: OperationControl,
    ) -> None:
        assert controller == spec.slurm.parent.writer
        control.checkpoint()

    def launcher(
        spec: BrowserResourceSpec, pid: int, control: OperationControl
    ) -> ProcessIdentity:
        control.checkpoint()
        return spec.slurm.parent.writer.model_copy(update={"process_id": pid})

    monkeypatch.setattr(step, "check_parent", parent)
    monkeypatch.setattr(step, "observe_launcher", launcher)
    monkeypatch.setattr(step, "observe_started", unit_started)
    monkeypatch.setattr(step, "observe_closed", unit_closed)
