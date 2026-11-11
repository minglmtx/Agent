"""Real fixed factory/resource/wire/CAS/files with explicit synthetic page/OS facts."""

from pathlib import Path
from lab_generate_skill.domain.lifecycle import ResourceOwner
from evidence_control_fixtures import EvidenceFixtureStore
import time
from urllib.parse import urlsplit
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.sites.map.browser_collection import MapBrowserCollection
from lab_generate_skill.sites.map.native_served_rules import RENDERER_READ
from lab_generate_skill.sites.map.native_surface_script import COMBINED_READ
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from map_browser_storage_fixtures import BrowserFilesCase
from browser_resource_fixtures import ResourceChannel
from browser_worker_fixtures import sources
from browsergym_fixtures import LoopbackAuthority
from browser_process_fixtures import case as synthetic_browser
from generator_worker_fixtures import unit_guard
from test_site_storage_admission import LiveGuard
from test_slurm_commands import guard
from map_browser_initialization_fixtures import (
    Page as ReadinessPage,
    Clock as ReadinessClock,
)
from lab_generate_skill.sites.map.native_view_scripts import READ, READINESS


class CollectionCase(BrowserFilesCase):
    def __init__(
        self,
        root: Path,
        patch: pytest.MonkeyPatch,
        *,
        owner: ResourceOwner | None = None,
        store: EvidenceFixtureStore | None = None,
        workspace: Path | None = None,
    ) -> None:
        super().__init__(root, patch, owner=owner, store=store, workspace=workspace)
        _, _, self.calls = synthetic_browser(patch)
        self.engine: BrowserGymEngine | None = None
        self.collector: MapBrowserCollection | None = None
        self.page: Any = None
        self.page_fault = ""
        outer = self

        class Page:
            def __init__(self, context: Any) -> None:
                self.url = "about:blank"
                self.context = context
                self.main_frame = object()
                self.listeners: list[Any] = []
                self.handler: Any = None
                self.reads = 0
                self.responses: list[Any] = []

            def route(self, pattern: str, handler: Any) -> None:
                outer.calls.append("route-before-navigation")
                self.handler = handler
                if outer.page_fault == "attach":
                    raise OSError("original route attachment failed")

            def unroute(self, pattern: str, handler: Any) -> None:
                assert self.handler == handler
                self.handler = None
                outer.calls.append("unroute")
                if outer.page_fault == "close":
                    raise OSError("original unroute acknowledgement lost")

            def on(self, event: str, handler: Any) -> None:
                assert event == "response"
                self.listeners.append(handler)

            def remove_listener(self, event: str, handler: Any) -> None:
                self.listeners.remove(handler)

            def goto(self, url: str, *, timeout: float) -> None:
                c = outer.collector
                assert c is not None and c.state == "active"
                assert c.native is not None and c.native.served is not None
                assert (
                    outer.reader.read(outer.configuration, guard()).record.state
                    == "acquired"
                )
                assert self.handler is not None and len(self.listeners) == 2
                outer.calls.append("navigate")
                self.url = url
                parsed = urlsplit(url)
                origin = parsed.scheme + "://" + parsed.netloc
                for name, source in c.native.served.expected.sources:
                    response = SimpleNamespace(
                        url=origin + "/assets/" + name,
                        request=SimpleNamespace(
                            resource_type="script", method="GET", frame=self.main_frame
                        ),
                        status=200,
                        from_service_worker=False,
                        body=lambda raw=source.encode(): raw,
                    )
                    self.responses.append(response)
                    for listener in self.listeners:
                        listener(response)

            def wait_for_function(
                self, expression: str, *, arg: Any, timeout: float
            ) -> None:
                assert READINESS in expression and timeout > 0
                outer.calls.append("native-ready-wait")

            def wait_for_timeout(self, ms: float) -> None:
                time.sleep(ms / 1000)

            def evaluate(self, expression: str, args: Any = None) -> Any:
                if expression in (READ, READINESS):
                    if outer.page_fault == "readiness":
                        raise OSError("original native readiness read failed")
                    if outer.page_fault == "autopan":
                        self.url = self.url.split("#")[0] + "#map=14/40.77/-73.97"
                    passive = ReadinessPage(ReadinessClock())
                    outer.calls.append(
                        "native-view" if expression == READ else "native-signal"
                    )
                    return passive.view if expression == READ else passive.signal
                self.reads += 1
                if outer.page_fault == "surface":
                    raise OSError("original complete page read failed")
                c = outer.collector
                assert (
                    c is not None
                    and c.native is not None
                    and c.native.served is not None
                )
                if expression == RENDERER_READ:
                    return dict(c.native.served.expected.renderer_functions)
                assert expression == COMBINED_READ
                return {
                    "surface": {"map_visible": True},
                    "route": {"rows": ["original route"]},
                }

        class Env:
            def __init__(self, *, task_entrypoint: Any, **kwargs: Any) -> None:
                self.entry = task_entrypoint
                self.context = SimpleNamespace(
                    on=lambda *args: None,
                    remove_listener=lambda *args: None,
                    close=lambda: outer.calls.append("context"),
                )
                self.browser = SimpleNamespace(
                    close=lambda: outer.calls.append("browser")
                )
                self.chat = SimpleNamespace(close=lambda: outer.calls.append("chat"))
                self.page = Page(self.context)
                outer.page = self.page
                self.task: Any = None

            def reset(self, *, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
                self.task = self.entry(seed)
                self.task.setup(self.page)
                return {}, {}

            def step(
                self, payload: str
            ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
                outer.calls.append("actual-action")
                return {}, 0.0, False, False, {}

        def factory(config: BrowserWorkerConfiguration) -> BrowserGymEngine:
            live = LiveGuard(
                unit_guard(outer.resource.spec.slurm.parent.writer, guard())
            )
            engine = build_browser_engine(
                config, LoopbackAuthority(), SystemClock(), worker_guard=live
            )
            assert isinstance(engine.process_collector, MapBrowserCollection)
            from lab_generate_skill.sites.map.browser_capture import MapBrowserCapture

            assert engine.collector is engine.process_collector or (
                isinstance(engine.collector, MapBrowserCapture)
                and engine.collector.process is engine.process_collector
            )
            outer.engine, outer.collector = engine, engine.process_collector
            return engine

        def channel(*args: Any, **kwargs: Any) -> ResourceChannel:
            result = ResourceChannel(outer.resource)
            result.service = BrowserService(factory, sources, unit_guard)
            outer.resource.channels.append(result)
            return result

        patch.setattr("browsergym.core.env.BrowserEnv", Env)
        patch.setattr(
            "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
            channel,
        )
