"""Real CAS/resource journal with a synthetic worker; no production permission."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import json
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from browser_step_fixtures import binding, install_unit_step
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.lifecycle import (
    RecoveryPlan,
    AllocationToken,
    OperationContext,
    ClosureReceipt,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from evidence_control_fixtures import EvidenceFixtureStore
from browsergym_fixtures import LoopbackAuthority
from browser_worker_fixtures import configuration, UnitBrowser, Channel, sources
from generator_worker_fixtures import unit_guard
from test_resource_journal import NoCancellation, context


class Authority(LoopbackAuthority):
    def __init__(self, store: EvidenceFixtureStore) -> None:
        self.store = store
        self.deny_start = False
        self.deny_started = False
        self.deny_close = False
        self.close_calls = 0

    def authorize_start(
        self,
        spec: BrowserResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.deny_start:
            raise PermissionError("unit launch denied")

    def verify_started(
        self,
        spec: BrowserResourceSpec,
        started: BrowserResourceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.deny_started:
            raise PermissionError("unit original process not verified")
        self.store.read(started.initial_observation_ref, control=control)
        self.store.read(started.initial_return_ref, control=control)

    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self.close_calls += 1
        proof = self.store.put(
            json.dumps(
                {"engineering_only": True, "attempt": attempt.model_dump(mode="json")}
            ).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="engineering-browser-close/1",
                visibility="private",
                producer="unit-authority",
            ),
            control=control,
        )
        return ClosureReceipt(
            token=spec.token,
            operation_id=operation.operation_id,
            status="unconfirmed" if self.deny_close else "closed",
            evidence=(proof,),
        )


@dataclass
class ResourceCase:
    spec: BrowserResourceSpec
    op: OperationContext
    journal: FileResourceJournal
    evidence: EvidenceFixtureStore
    controls: OperationGuards
    clock: SystemClock
    authority: Authority
    channels: list["ResourceChannel"]


class ResourceChannel(Channel):
    def __init__(self, case: ResourceCase) -> None:
        self.case = case
        self.engine = UnitBrowser(case.spec.configuration)
        super().__init__(BrowserService(lambda c: self.engine, sources, unit_guard))
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
        if self.start_error is not None:
            raise self.start_error
        self.process_id = current_process_identity().process_id + 10000002

    def finish(self, control: OperationControl) -> ProcessTermination:
        super().finish(control)
        value = ProcessTermination(self.process_id, "reaped", 0, False)
        self.capture = CommandCapture(self.capture.argv, 0, b"", b"", True, value)
        return value

    def abort(self, control: OperationControl) -> ProcessTermination:
        self.aborts += 1
        value = (
            ProcessTermination(self.process_id, "reaped", -9, True)
            if self.process_id is not None
            else ProcessTermination(None, "not_started", None, False)
        )
        self.engine.state = "closed"
        self.capture = CommandCapture(
            self.capture.argv, value.returncode, b"", b"", False, value
        )
        return value


def resource_case(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    config: BrowserWorkerConfiguration | None = None,
    store: EvidenceFixtureStore | None = None,
    real_step: bool = False,
    declared_token: AllocationToken | None = None,
) -> ResourceCase:
    for name in ("evidence", "journal"):
        (root / name).mkdir()
    store = store if store is not None else EvidenceFixtureStore(root / "evidence")

    def put(raw: bytes, schema: str) -> EvidenceRef:
        return store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit",
            ),
        )

    if config is None:
        config = configuration()
        config = config.model_copy(
            update={
                "spec": config.spec.model_copy(
                    update={
                        "scope": config.spec.scope.model_copy(
                            update={
                                "owner": config.spec.scope.owner.model_copy(
                                    update={"job_id": "4752096"}
                                )
                            }
                        )
                    }
                )
            }
        )
    scope = config.spec.scope
    recovery = RecoveryPlan(
        recovery_id="browser-close",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=put(b"{}", "engineering-baseline/1"),
        restore_component_id="browser-close",
        restore_component_version="1",
        state_coverage=("browser-processes",),
    )
    token = declared_token or AllocationToken(
        allocation_id="browser-allocation",
        owner=scope.owner,
        scope="attempt",
        attempt_id=scope.attempt_id,
        resource_kind="browser",
        expected_resource_id="browser-instance",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=put(recovery.model_dump_json().encode(), "recovery-plan/1"),
    )
    spec = BrowserResourceSpec(
        token=token,
        configuration=config,
        slurm=binding(scope.owner.job_id, real=real_step),
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    journal = FileResourceJournal(root / "journal", scope.owner, controls, store)
    case = ResourceCase(
        spec,
        context(token, "acquire"),
        journal,
        store,
        controls,
        clock,
        Authority(store),
        [],
    )

    def channel(*args: object, **kwargs: object) -> ResourceChannel:
        result = ResourceChannel(case)
        case.channels.append(result)
        return result

    if not real_step:
        monkeypatch.setattr(
            "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
            channel,
        )
        install_unit_step(monkeypatch)
    return case
