"""Explicit synthetic page callback/readout fixtures; native HTTP remains real."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import time
from typing import Any
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.observation import Observation, BrowserTab
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.sites.map.native_relay import NativeMapRelay
from lab_generate_skill.sites.map.native_route_collector import (
    MapNativeRequestCollector,
)
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter
from map_artifact_fixtures import case, Authority
from browsergym_fixtures import spec, operation
from test_slurm_commands import guard


def selected_spec(writer: MapArtifactWriter, url: str) -> BrowserSessionSpec:
    source = spec(url)
    task = PublicTask(
        identity=writer.plan.scope.task,
        goal="Exercise the controlled MapData fixture",
        start_url=url,
        allowed_actions=source.task.allowed_actions,
    )
    return BrowserSessionSpec.model_validate(
        {**source.model_dump(), "scope": writer.plan.scope, "task": task}
    )


class Page:
    url = "about:blank"
    fault = ""

    def __init__(self) -> None:
        self.handler: Any = None
        self.routes = 0
        self.unroutes = 0
        self.waits = 0
        self.renderer_waits = 0

    def route(self, pattern: str, handler: Any) -> None:
        self.handler = handler
        self.routes += 1
        if self.fault == "route":
            raise OSError("partial route installation")

    def unroute(self, pattern: str, handler: Any) -> None:
        assert handler is self.handler
        self.unroutes += 1
        if self.fault == "unroute":
            raise OSError("original route detach failed")
        self.handler = None

    def wait_for_timeout(self, ms: float) -> None:
        self.waits += 1
        time.sleep(ms / 1000)

    def wait_for_function(self, expression: str, *, timeout: float) -> None:
        self.renderer_waits += 1
        assert "jQuery.active" in expression and timeout > 0
        if self.fault == "renderer":
            raise TimeoutError("original renderer still pending")


class Route:
    def __init__(
        self,
        origin: str,
        *,
        method: str = "GET",
        kind: str = "xhr",
        query: str = "bbox=0,0,0.5,0.5",
        fault: str = "",
    ) -> None:
        self.request = SimpleNamespace(
            url=origin + "/api/0.6/map?" + query,
            method=method,
            resource_type=kind,
            headers={
                "Cookie": "private",
                "Authorization": "private",
                "Referer": origin + "/",
                "accept": "application/xml",
            },
        )
        self.calls: list[dict[str, Any]] = []
        self.aborts = 0
        self.fault = fault

    def continue_(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.fault == "continue":
            raise OSError("original continue reply lost")

    def abort(self, reason: str) -> None:
        assert reason == "failed"
        self.aborts += 1
        if self.fault == "abort":
            raise OSError("original abort also failed")


def collection(
    root: Path, origin: str
) -> tuple[
    MapNativeRequestCollector, MapArtifactWriter, Authority, Page, BrowserSessionSpec
]:
    writer, authority = case(root)
    writer.initialize(guard())
    relay = NativeMapRelay(origin, writer, guard(60), max_requests=4)
    collector = MapNativeRequestCollector(writer.plan, relay)
    return collector, writer, authority, Page(), selected_spec(writer, origin + "/")


def readout(
    value: BrowserSessionSpec, sequence: int, *, terminal: bool = False
) -> BrowserReadout:
    action = (
        None
        if sequence == 0
        else BrowserAction(
            action_id=f"action-{sequence}",
            protocol_id="browsergym-highlevel-v1",
            name="send_msg_to_user" if terminal else "click",
            payload="send_msg_to_user('done')" if terminal else "click('1')",
        )
    )
    return BrowserReadout(
        schema_version=(
            "browser-initial-return/1" if sequence == 0 else "browser-step-return/1"
        ),
        scope=value.scope,
        operation=operation(value, f"readout-{sequence}"),
        action=action,
        observation=Observation(
            observation_id=f"observation-{sequence}",
            task=value.task.identity,
            context_id=value.scope.context_id,
            attempt_id=value.scope.attempt_id,
            sequence=sequence,
            captured_at=datetime.now(timezone.utc),
            tabs=(
                BrowserTab(
                    tab_id="tab", url=value.task.start_url, title="Controlled fixture"
                ),
            ),
            active_tab_id="tab",
            state="ready",
            text="Controlled public content",
        ),
        events=(),
        environment_reward=0.0,
        terminated=False,
        truncated=False,
        protocol_terminal=terminal,
    )
