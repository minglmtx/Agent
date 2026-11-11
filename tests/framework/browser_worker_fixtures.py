"""Synthetic service/channel fixtures; actual installation is tested separately."""

from datetime import datetime, timezone
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_initialization import PublicNavigation
from lab_generate_skill.adapters.browsergym.worker_protocol import (
    WORKER_MODULE,
    decode_command,
)
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, BrowserTab
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
    InstalledReleaseModule,
)
from lab_generate_skill.ports.browser_session import BrowserState
from lab_generate_skill.ports.lifecycle import OperationControl
from browsergym_fixtures import spec, operation, LoopbackAuthority, CHROMIUM
from storage_installation_fixtures import storage_installation, unit_storage_sources
from generator_worker_fixtures import unit_guard

LIBS = "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs"


def configuration(
    installation: ReleaseInstallation | None = None, url: str = "http://127.0.0.1:8000/"
) -> BrowserWorkerConfiguration:
    return BrowserWorkerConfiguration(
        spec=spec(url),
        initialization=PublicNavigation(),
        installation=installation or storage_installation(),
        playwright_browsers_path=CHROMIUM.rsplit("/", 3)[0],
        library_directories=(LIBS,),
    )


def sources(
    installation: ReleaseInstallation, control: OperationControl
) -> InstalledReleaseSources:
    control.checkpoint()
    value = unit_storage_sources(installation)
    module = InstalledReleaseModule(
        name=WORKER_MODULE, filename=value.package_root + "/bootstrap/browser_worker.py"
    )
    return value.model_copy(
        update={
            "modules": tuple(sorted((*value.modules, module), key=lambda m: m.name))
        }
    )


class UnitBrowser:
    def __init__(self, config: BrowserWorkerConfiguration) -> None:
        self.spec = config.spec
        self.state: BrowserState = "new"
        self.last_readout: BrowserReadout | None = None
        self.calls: list[str] = []
        self.failure: BaseException | None = None
        self.close_failure: BaseException | None = None

    def value(
        self, op: OperationContext, action: BrowserAction | None
    ) -> BrowserReadout:
        observed = Observation(
            observation_id=op.operation_id,
            task=self.spec.task.identity,
            context_id=self.spec.scope.context_id,
            attempt_id=self.spec.scope.attempt_id,
            sequence=0 if action is None else 1,
            captured_at=datetime.now(timezone.utc),
            tabs=(
                BrowserTab(tab_id="tab", url=self.spec.task.start_url, title="Page"),
            ),
            active_tab_id="tab",
            state="ready",
            text="Page",
        )
        self.last_readout = BrowserReadout(
            schema_version=(
                "browser-initial-return/1"
                if action is None
                else "browser-step-return/1"
            ),
            scope=self.spec.scope,
            operation=op,
            action=action,
            observation=observed,
            events=(),
            environment_reward=0.0,
            terminated=False,
            truncated=False,
            protocol_terminal=False,
        )
        return self.last_readout

    def start(
        self, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout:
        control.checkpoint()
        self.calls.append("start")
        self.state = "ready"
        return self.value(operation, None)

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> BrowserReadout:
        control.checkpoint()
        self.calls.append("step")
        value = self.value(operation, action)
        if self.failure is not None:
            raise self.failure
        return value

    def quarantine(self) -> None:
        self.state = "quarantined"

    def close(self, operation: OperationContext, *, control: OperationControl) -> None:
        control.checkpoint()
        if self.state == "closed":
            return
        self.calls.append("close")
        if self.close_failure is not None:
            raise self.close_failure
        self.state = "closed"


class Channel:
    def __init__(self, service: BrowserService) -> None:
        self.service = service
        self.calls: list[bytes] = []
        self.aborts = 0
        self.finishes = 0
        self.capture = CommandCapture(("/unit/browser",), None, b"", b"", False)
        self.bad_reply: bytes | None = None
        self.abort_failure: BaseException | None = None

    def exchange(self, payload: bytes, control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(payload)
        reply = self.service.handle(decode_command(payload)).model_dump_json().encode()
        return self.bad_reply if self.bad_reply is not None else reply

    def abort(self, control: OperationControl) -> ProcessTermination:
        self.aborts += 1
        if self.abort_failure is not None:
            raise self.abort_failure
        return ProcessTermination(123, "reaped", -9, True)

    def finish(self, control: OperationControl) -> ProcessTermination:
        self.finishes += 1
        return ProcessTermination(123, "reaped", 0, False)


def case() -> tuple[UnitBrowser, BrowserService, Channel, SupervisedBrowserSession]:
    config = configuration()
    engine = UnitBrowser(config)
    service = BrowserService(lambda cfg: engine, sources, unit_guard)
    channel = Channel(service)
    client = SupervisedBrowserSession(
        channel, "browser-session", config, LoopbackAuthority()
    )
    return engine, service, channel, client


def action() -> BrowserAction:
    return BrowserAction(
        action_id="fill",
        protocol_id="browsergym-highlevel-v1",
        name="fill",
        payload="fill('a', 'value')",
    )
