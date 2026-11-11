"""Explicit unit query/kernel substitutes; no production admission defaults."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.slurm import allocation as module
from lab_generate_skill.adapters.slurm.commands import (
    CommandCapture,
    SlurmCommandRunner,
)
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.slurm.linux_cgroups import (
    KernelCgroupObservation,
)
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.domain.scheduler import (
    SlurmExecutionIdentity,
    SlurmJobObservation,
)
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_slurm_allocation_codecs import FIXTURES, original_identity
from test_slurm_probe import NoCancel


class QueryRunner(SlurmCommandRunner):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, ...]] = []
        self.controller = (FIXTURES / "controller.json").read_bytes()
        self.gpu = (FIXTURES / "gpu.xml").read_bytes()
        self.fail: Exception | None = None
        self.complete = True
        self.ending: ProcessTermination | None = ProcessTermination(
            100, "reaped", 0, False
        )

    def run(self, argv: tuple[str, ...], control: OperationControl) -> CommandCapture:
        control.checkpoint()
        self.calls.append(argv)
        if self.fail is not None:
            raise self.fail
        raw = self.controller if argv[0].endswith("scontrol") else self.gpu
        return CommandCapture(argv, 0, raw, b"", self.complete, self.ending)


class Probe:
    def __init__(self, store: FileEvidenceStore) -> None:
        self.reference = store.put(
            b"unit scheduler bytes",
            EvidenceMetadata(
                media_type="application/json",
                content_schema="slurm-probe/1",
                visibility="private",
                producer="unit",
            ),
        )
        self.calls = 0
        self.changes: dict[str, object] = {}
        self.change_after = 0
        self.fail: Exception | None = None

    def observe(
        self, execution: SlurmExecutionIdentity, op: OperationContext
    ) -> SlurmJobObservation:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        values: dict[str, object] = dict(
            execution=execution,
            observed_at=datetime.now(timezone.utc),
            accounting_state="RUNNING",
            exit_status=0,
            exit_signal=0,
            queue_state="RUNNING",
            evidence=self.reference,
        )
        if self.calls > self.change_after:
            values.update(self.changes)
        return SlurmJobObservation.model_validate(values)


class Case:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = FileEvidenceStore(root)
        self.clock = SystemClock()
        self.controls = OperationGuards(self.clock, NoCancel())
        self.probe = Probe(self.store)
        self.runner = QueryRunner()
        self.execution = original_identity()
        self.writer = ProcessIdentity(
            node_id="a0125",
            boot_id="4b4dd338-23e5-465e-95d6-f21a9d346b94",
            process_id=3910250,
            start_ticks=55194394,
        )
        self.membership = SlurmCgroupMembership(
            job_id=self.execution.raw_job_id,
            step_id="batch",
            writer=self.writer,
            uid=self.execution.uid,
            user_path="/sys/fs/cgroup/system.slice/slurmstepd.scope/job_4751471/step_batch/user",
            mount_id=138,
            device=26,
            user_inode=100,
            task_inode=101,
        )
        self.kernel_calls = 0
        self.kernel_error: Exception | None = None
        self.drift = False
        monkeypatch.setattr(module, "observe_current_cgroup", self.kernel)

    def kernel(
        self,
        execution: SlurmExecutionIdentity,
        writer: ProcessIdentity,
        control: OperationControl,
    ) -> KernelCgroupObservation:
        control.checkpoint()
        self.kernel_calls += 1
        if self.kernel_error is not None:
            raise self.kernel_error
        membership = self.membership
        if self.drift and self.kernel_calls > 1:
            membership = membership.model_copy(update={"user_inode": 102})
        return KernelCgroupObservation(membership, KernelCapture((), ()))

    def verifier(self) -> module.SlurmAllocationVerifier:
        return module.SlurmAllocationVerifier(
            self.store,
            self.controls,
            self.clock,
            self.probe,
            self.runner,
            scontrol=Path("/usr/bin/scontrol"),
            nvidia_smi=Path("/usr/bin/nvidia-smi"),
        )
