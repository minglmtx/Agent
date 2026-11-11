"""Explicit engineering admission only; never installed as a production authority."""

import os
import socket
from dataclasses import dataclass
from typing import TypedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.domain.actor_step import (
    ActorSlurmBinding,
    ActorStepStarted,
    ActorStepClosed,
    ActorStepCleanup,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.slurm.probe import AccountingSlurmProbe
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.models.actor_resource_records import phase
from lab_generate_skill.adapters.models.actor_step import (
    ActorStepState,
    observe_closed,
)
from test_linux_cgroups import actual_slurm_execution
from lab_generate_skill.domain.lifecycle import (
    ResourceOwner,
    RecoveryPlan,
    AllocationToken,
    OperationContext,
)
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.actor_resources import ActorResourceAuthority
from lab_generate_skill.runtime.lifecycle import OperationGuards
from installed_source_fixtures import InstalledFixture
from actor_engine_fixtures import setup
from actor_release_fixtures import freeze_model_release
from test_resource_journal import NoCancellation


from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree, pin_user_tree


class EngineeringAuthority:
    """Verify this controlled test child only, with no formal source admission."""

    def __init__(self, evidence: FileEvidenceStore) -> None:
        self.evidence = evidence
        self._pin: PinnedUserTree | None = None
        self.start_denied = False
        self.close_denied = False
        self.workers: list[ProcessIdentity] = []
        self.closed: list[ProcessTermination] = []

    def authorize_start(
        self,
        spec: ActorResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.start_denied:
            raise PermissionError("engineering start denied")

    def verify_started(
        self,
        spec: ActorResourceSpec,
        started: ActorStepStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        worker = started.controller.target.worker.writer
        assert started.controller.target.launcher.process_id != worker.process_id
        assert worker.node_id == socket.gethostname()
        assert (
            worker.boot_id
            == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        )
        assert (
            parse_process_start(
                Path(f"/proc/{worker.process_id}/stat").read_bytes(), worker.process_id
            )
            == worker.start_ticks
        )
        assert worker.process_id != os.getpid()
        self._pin = pin_user_tree(started.controller.target.worker, control)
        self.workers.append(worker)

    def _verify_closed(
        self,
        spec: ActorResourceSpec,
        cleanup: ActorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> ActorStepClosed | None:
        control.checkpoint()
        if self.close_denied:
            raise PermissionError("engineering close unconfirmed")
        closed = observe_closed(
            spec,
            ActorStepState(
                start_attempted=cleanup.start_attempted,
                launcher=cleanup.launcher,
                target=cleanup.target,
                started=cleanup.started,
            ),
            termination,
            self.evidence,
            control,
            self._pin,
        )
        started = cleanup.started
        assert (
            termination.state in ("reaped", "not_started")
            and not termination.cleanup_errors
        )
        if closed is not None:
            assert termination.process_id == closed.target.launcher.process_id
            assert closed.quiescence.original == closed.target.worker
            assert closed.quiescence.writer_status in ("missing", "reused")
        else:
            assert termination.state == "not_started"
        if started is not None:
            assert closed is not None and closed.target == started.controller.target
        self.closed.append(termination)
        return closed

    def verify_closed(
        self,
        spec: ActorResourceSpec,
        cleanup: ActorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> ActorStepClosed | None:
        primary: BaseException | None = None
        try:
            return self._verify_closed(spec, cleanup, termination, op, control)
        except BaseException as error:
            primary = error
            raise
        finally:
            pinned, self._pin = self._pin, None
            if pinned is not None:
                try:
                    pinned.close()
                except BaseException as error:
                    raise BaseExceptionGroup(
                        "Engineering verification and pin cleanup failed",
                        ([primary] if primary else []) + [error],
                    ) from None


class ResourceDependencies(TypedDict):
    journal: FileResourceJournal
    evidence: FileEvidenceStore
    controls: OperationGuards
    clock: SystemClock
    authority: ActorResourceAuthority
    workspace_root: Path
    allocation_verifier: SlurmAllocationVerifier


@dataclass
class ResourceCase:
    spec: ActorResourceSpec
    op: OperationContext
    journal: FileResourceJournal
    evidence: FileEvidenceStore
    controls: OperationGuards
    clock: SystemClock
    authority: EngineeringAuthority
    workspace_root: Path
    allocation_verifier: SlurmAllocationVerifier

    def dependencies(self) -> ResourceDependencies:
        return ResourceDependencies(
            journal=self.journal,
            evidence=self.evidence,
            controls=self.controls,
            clock=self.clock,
            authority=self.authority,
            workspace_root=self.workspace_root,
            allocation_verifier=self.allocation_verifier,
        )


def resource_case(
    root: Path,
    executable: Path,
    *,
    installation: InstalledFixture | None = None,
    engine_config: ActorEngineConfig | None = None,
) -> ResourceCase:
    root.mkdir(exist_ok=True)
    for child in ("evidence", "journal", "model"):
        (root / child).mkdir()
    engine, loader, _, _, _ = setup(root / "model")
    if engine_config is not None:
        engine = ResidentActorEngine(engine.artifact, engine_config, loader=loader)
    evidence = FileEvidenceStore(root / "evidence")

    def put(payload: bytes, schema: str) -> EvidenceRef:
        return evidence.put(
            payload,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="engineering-test",
            ),
        )

    execution, _ = actual_slurm_execution()
    owner = ResourceOwner(
        run_id="run",
        owner_id="owner",
        job_id=execution.job_id,
        worker_id="engineering-parent",
    )
    baseline = put(b"{}", "engineering-baseline/1")
    plan = RecoveryPlan(
        recovery_id="actor-close",
        owner=owner,
        baseline_ref=baseline,
        restore_component_id="actor-close",
        restore_component_version="1",
        state_coverage=("worker",),
    )
    token = AllocationToken(
        allocation_id="actor-allocation",
        owner=owner,
        scope="batch",
        resource_kind="actor",
        expected_resource_id="engineering-actor",
        provider_id="fixed-actor-worker",
        provider_version="1",
        recovery_ref=put(plan.model_dump_json().encode(), "recovery-plan/1"),
    )
    release_ref, model_ref = freeze_model_release(
        root / "release",
        evidence,
        engine.artifact,
        engine.config,
        installation=installation.manifest if installation is not None else None,
    )
    op = OperationContext(
        operation_id="actor-start",
        run_id="run",
        owner_id="owner",
        allocation_id=token.allocation_id,
        recovery_ref=token.recovery_ref,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    controls = OperationGuards(SystemClock(), NoCancellation())
    clock = SystemClock()
    runner = SlurmCommandRunner()
    probe = AccountingSlurmProbe(
        evidence,
        controls,
        clock,
        runner,
        sacct=Path("/usr/bin/sacct"),
        squeue=Path("/usr/bin/squeue"),
    )
    verifier = SlurmAllocationVerifier(
        evidence,
        controls,
        clock,
        probe,
        runner,
        scontrol=Path("/usr/bin/scontrol"),
        nvidia_smi=Path("/usr/bin/nvidia-smi"),
    )
    allocation = verifier.observe(
        execution, current_process_identity(), phase(op, "allocation-pin")
    )
    spec = ActorResourceSpec(
        token=token,
        release_ref=release_ref,
        model_binding_ref=model_ref,
        python_executable=str(executable),
        slurm=ActorSlurmBinding(
            allocation=allocation,
            srun_executable="/usr/bin/srun",
            scontrol_executable="/usr/bin/scontrol",
        ),
        artifact=engine.artifact,
        engine_config=engine.config,
    )
    return ResourceCase(
        spec,
        op,
        FileResourceJournal(root / "journal", owner, controls, evidence),
        evidence,
        controls,
        SystemClock(),
        EngineeringAuthority(evidence),
        (
            Path(os.path.commonpath((root, installation.workspace)))
            if installation is not None
            else root
        ),
        verifier,
    )
