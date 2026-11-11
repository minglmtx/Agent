"""Explicit synthetic BrowserEnv; lifecycle ordering only, no website claims."""

from datetime import datetime
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.observation import Observation, BrowserTab
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from browsergym_fixtures import spec, LoopbackAuthority, CHROMIUM


class Collector:
    def __init__(self, calls: list[str], fault: str = "") -> None:
        self.calls, self.fault = calls, fault
        self.readouts: list[BrowserReadout] = []
        self.sealed = False

    def visit(self, name: str, control: OperationControl) -> None:
        control.checkpoint()
        self.calls.append(name)
        if name == self.fault:
            raise OSError(name)

    def attach(
        self, page: Any, spec: BrowserSessionSpec, control: OperationControl
    ) -> None:
        assert page.url == "about:blank"
        self.visit("attach", control)

    def before_action(self, control: OperationControl) -> None:
        self.visit("before_action", control)
        if self.sealed:
            raise ValueError("process evidence sealed")

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        self.readouts.append(readout)
        assert page.url == readout.observation.tabs[0].url
        self.visit("observe", control)

    def close(self, control: OperationControl) -> None:
        self.visit("collector_close", control)


def case(
    monkeypatch: pytest.MonkeyPatch, fault: str = "", *, enabled: bool = True
) -> tuple[BrowserGymEngine, Collector, list[str]]:
    import browsergym.core as core  # type: ignore[import-untyped]
    import browsergym.core.env as env_module  # type: ignore[import-untyped]
    import lab_generate_skill.adapters.browsergym.engine as engine_module

    calls: list[str] = []
    collector = Collector(calls, fault)
    frozen = spec()

    class Item:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(self.name)

        def teardown(self) -> None:
            self.close()

        def on(self, *args: Any) -> None:
            pass

        def remove_listener(self, *args: Any) -> None:
            pass

    class Initializer:
        def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
            control.checkpoint()
            calls.append("navigate")
            page.url = task.start_url

    class Env:
        def __init__(self, *, task_entrypoint: Any, **kwargs: Any) -> None:
            self.entry = task_entrypoint
            self.context, self.browser, self.chat = (
                Item(n) for n in ("context", "browser", "chat")
            )
            self.page = SimpleNamespace(url="about:blank", context=self.context)
            self.task: Any = None

        def reset(self, *, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
            self.task = self.entry(seed)
            self.task.setup(self.page)
            return {}, {}

        def step(
            self, payload: str
        ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
            calls.append("actual_action")
            return {}, 0.0, False, False, {}

    def project(
        raw: dict[str, Any],
        spec: BrowserSessionSpec,
        sequence: int,
        captured_at: datetime,
    ) -> Observation:
        calls.append("project")
        return Observation(
            observation_id=f"observation-{sequence}",
            task=spec.task.identity,
            context_id=spec.scope.context_id,
            attempt_id=spec.scope.attempt_id,
            sequence=sequence,
            captured_at=captured_at,
            tabs=(BrowserTab(tab_id="tab", url=spec.task.start_url, title="Fixture"),),
            active_tab_id="tab",
            state="ready",
            text="Fixture",
        )

    driver = SimpleNamespace(
        chromium=SimpleNamespace(executable_path=CHROMIUM),
        stop=lambda: calls.append("driver"),
    )
    monkeypatch.setattr(core, "_PLAYWRIGHT", None)
    monkeypatch.setattr(core, "_get_global_playwright", lambda: driver)
    monkeypatch.setattr(env_module, "BrowserEnv", Env)
    monkeypatch.setattr(engine_module, "project", project)
    return (
        BrowserGymEngine(
            frozen,
            LoopbackAuthority(),
            SystemClock(),
            Initializer(),
            process_collector=collector if enabled else None,
        ),
        collector,
        calls,
    )
