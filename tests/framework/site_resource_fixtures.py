"""Actual CAS/journal, explicitly synthetic worker and kernel facts for unit tests."""

from dataclasses import dataclass
from pathlib import Path
import json
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.adapters.sites import step
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteSlurmBinding,
    SiteResourceReady,
    SiteResourceAttempt,
    SiteStepClosed,
)
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteWorkerReady,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.slurm_quiescence import SlurmUserQuiescence
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.lifecycle import (
    RecoveryPlan,
    OperationContext,
    ClosureReceipt,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.slurm.step_launch import site_step_name
from evidence_control_fixtures import EvidenceFixtureStore
from site_worker_fixtures import (
    configuration,
    Instance,
    Channel,
    Authority as WorkerAuthority,
    sources,
)
from generator_worker_fixtures import unit_guard
from browser_step_fixtures import binding
from test_resource_journal import NoCancellation, context


class Authority(WorkerAuthority):
    def __init__(self, store: EvidenceFixtureStore) -> None:
        super().__init__()
        self.store = store
        self.deny: str | None = None
        self.close_calls = 0

    def authorize_spawn(
        self, spec: SiteResourceSpec, op: OperationContext, control: OperationControl
    ) -> None:
        control.checkpoint()
        if self.deny == "spawn":
            raise PermissionError("unit spawn denied")

    def verify_ready(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self.store.read(ready.evidence, control=control)
        if self.deny == "ready":
            raise PermissionError("unit ready denied")

    def verify_started(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        started: SiteInstanceStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.deny == "started":
            raise PermissionError("unit started denied")

    def verify_closed(
        self,
        spec: SiteResourceSpec,
        attempt: SiteResourceAttempt,
        termination: ProcessTermination | None,
        closed: SiteStepClosed | None,
        op: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self.close_calls += 1
        ref = self.store.put(
            json.dumps(
                {"engineering_only": True, "attempt": attempt.model_dump(mode="json")}
            ).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="engineering-site-close/1",
                visibility="private",
                producer="unit",
            ),
            control=control,
        )
        return ClosureReceipt(
            token=spec.token,
            operation_id=op.operation_id,
            status="unconfirmed" if self.deny == "closed" else "closed",
            evidence=(ref,),
        )


@dataclass
class Case:
    spec: SiteResourceSpec
    op: OperationContext
    journal: FileResourceJournal
    evidence: EvidenceFixtureStore
    controls: OperationGuards
    clock: SystemClock
    authority: Authority
    channels: list["ResourceChannel"]


class ResourceInstance(Instance):
    def __init__(self, case: Case) -> None:
        super().__init__(case.spec.configuration)
        self.case = case

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        record = self.case.journal.read(self.case.spec.token, self.case.op)
        assert record.state == "acquired"
        raw = json.loads(self.case.evidence.read(record.events[-1].evidence[0]))
        assert raw["details"]["site_started"] is False
        assert raw["details"]["ready"]["worker"]["owner_guard"]
        return super().start(control)


class ResourceChannel(Channel):
    def __init__(self, case: Case) -> None:
        self.case = case
        self.engine = ResourceInstance(case)
        super().__init__(SiteService(lambda config: self.engine, sources, unit_guard))
        self.process_id: int | None = None
        self.starts = 0
        self.start_error: BaseException | None = None

    def start(self, control: OperationControl) -> None:
        control.checkpoint()
        assert (
            self.case.journal.read(self.case.spec.token, self.case.op).state
            == "acquiring"
        )
        self.starts += 1
        if self.start_error:
            raise self.start_error
        self.process_id = self.case.spec.slurm.parent.writer.process_id + 10000002

    def finish(self, control: OperationControl) -> ProcessTermination:
        super().finish(control)
        return self._capture(False)

    def abort(self, control: OperationControl) -> ProcessTermination:
        super().abort(control)
        return self._capture(True)

    def _capture(self, aborted: bool) -> ProcessTermination:
        value = ProcessTermination(
            self.process_id,
            "reaped" if self.process_id else "not_started",
            (-9 if aborted else 0) if self.process_id else None,
            aborted and self.process_id is not None,
        )
        self.capture = CommandCapture(
            self.capture.argv, value.returncode, b"", b"", not aborted, value
        )
        return value


def raw(store: EvidenceStore, control: OperationControl) -> EvidenceRef:
    return store.put(
        b'{"engineering_only":true}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="site-step-raw/1",
            visibility="private",
            producer="unit",
        ),
        control=control,
    )


def ready(
    spec: SiteResourceSpec,
    state: step.SiteStepState,
    worker: SiteWorkerReady,
    store: EvidenceStore,
    control: OperationControl,
) -> SiteResourceReady:
    assert state.launcher is not None
    parent = spec.slurm.parent
    membership = parent.model_copy(
        update={
            "step_id": "0",
            "writer": worker.owner_guard.worker,
            "user_inode": parent.user_inode + 100,
            "task_inode": parent.task_inode + 100,
            "user_path": parent.user_path.replace("step_batch", "step_0"),
        }
    )
    state.target = SlurmStepTarget(
        execution=spec.slurm.execution,
        resources="cpu_only",
        step_name=site_step_name(spec.token),
        launcher=state.launcher,
        worker=membership,
    )
    state.ready = SiteResourceReady(
        worker=worker,
        controller=SlurmControllerStep(
            target=state.target,
            started_at_epoch=spec.slurm.execution.started_at_epoch,
            gpu_type=None,
            memory="1M",
        ),
        evidence=raw(store, control),
    )
    return state.ready


def closed(
    spec: SiteResourceSpec,
    state: step.SiteStepState,
    termination: ProcessTermination | None,
    store: EvidenceStore,
    control: OperationControl,
    *,
    metadata_control: OperationControl,
) -> SiteStepClosed | None:
    if state.target is None:
        if termination is not None and termination.state == "not_started":
            return None
        raise ValueError("Unknown original target")
    return SiteStepClosed(
        target=state.target,
        quiescence=SlurmUserQuiescence(
            original=state.target.worker,
            observer=spec.slurm.parent.writer,
            writer_status="missing",
        ),
        evidence=raw(store, metadata_control),
    )


def resource_case(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    config: SiteWorkerConfiguration | None = None,
    real_step: bool = False,
    store: EvidenceFixtureStore | None = None,
) -> Case:
    for name in ("evidence", "journal"):
        (root / name).mkdir(mode=0o700)
    store = store if store is not None else EvidenceFixtureStore(root / "evidence")
    config = config or configuration(job_id="4752096")
    baseline = store.put(
        b"{}",
        EvidenceMetadata(
            media_type="application/json",
            content_schema="engineering-baseline/1",
            visibility="private",
            producer="unit",
        ),
    )
    recovery = RecoveryPlan(
        recovery_id="site-close",
        owner=config.token.owner,
        baseline_ref=baseline,
        restore_component_id="site-close",
        restore_component_version="2",
        state_coverage=("site-processes",),
    )
    recovery_ref = store.put(
        recovery.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="recovery-plan/1",
            visibility="private",
            producer="unit",
        ),
    )
    config = SiteWorkerConfiguration.model_validate(
        {
            **config.model_dump(),
            "token": config.token.model_copy(update={"recovery_ref": recovery_ref}),
        }
    )
    old_binding = binding(config.token.owner.job_id, real=real_step)
    spec = SiteResourceSpec(
        configuration=config,
        slurm=SiteSlurmBinding.model_validate(
            {**old_binding.model_dump(), "schema_version": "site-slurm-binding/1"}
        ),
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    journal = FileResourceJournal(root / "journal", spec.token.owner, controls, store)
    c = Case(
        spec,
        context(spec.token, "site-acquire"),
        journal,
        store,
        controls,
        clock,
        Authority(store),
        [],
    )
    if not real_step:

        def channel(*args: object, **kwargs: object) -> ResourceChannel:
            result = ResourceChannel(c)
            c.channels.append(result)
            return result

        def parent(
            spec: SiteResourceSpec,
            controller: ProcessIdentity,
            control: OperationControl,
        ) -> None:
            assert controller == spec.slurm.parent.writer
            control.checkpoint()

        def launcher(
            spec: SiteResourceSpec, pid: int, control: OperationControl
        ) -> ProcessIdentity:
            control.checkpoint()
            return spec.slurm.parent.writer.model_copy(update={"process_id": pid})

        monkeypatch.setattr(
            "lab_generate_skill.adapters.sites.resource.FramedProcessSession", channel
        )
        monkeypatch.setattr(step, "check_parent", parent)
        monkeypatch.setattr(step, "observe_launcher", launcher)
        monkeypatch.setattr(step, "observe_ready", ready)
        monkeypatch.setattr(step, "observe_closed", closed)
    return c
