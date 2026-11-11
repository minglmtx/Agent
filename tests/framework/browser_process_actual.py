"""Actual loopback Chromium process collection; no Map services or Actor."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.ports.lifecycle import OperationControl
from browsergym_fixtures import spec, operation, LoopbackAuthority, CHROMIUM
from test_slurm_commands import guard


class ProcessCapture:
    def __init__(self, fail_after_return: bool) -> None:
        self.fail_after_return = fail_after_return
        self.page: Any = None
        self.responses: list[tuple[str, int]] = []
        self.readouts: list[BrowserReadout] = []
        self.sealed = False
        self.close_calls = 0

    def response(self, response: Any) -> None:
        self.responses.append((response.url, response.status))

    def attach(
        self, page: Any, spec: BrowserSessionSpec, control: OperationControl
    ) -> None:
        control.checkpoint()
        assert self.page is None and page.url == "about:blank"
        self.page = page
        page.context.on("response", self.response)

    def before_action(self, control: OperationControl) -> None:
        control.checkpoint()
        if self.sealed:
            raise ValueError("process evidence sealed")

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        control.checkpoint()
        assert page is self.page
        assert (readout.observation.tabs[0].url, 200) in self.responses
        self.readouts.append(readout)
        if self.fail_after_return and readout.observation.sequence == 1:
            raise OSError("injected process evidence failure after actual return")

    def close(self, control: OperationControl) -> None:
        control.checkpoint()
        self.close_calls += 1
        if self.page is not None:
            self.page.context.remove_listener("response", self.response)
            self.page = None


def test_actual_fixture_preflight_without_browser() -> None:
    from lab_generate_skill.ports.browser_process import BrowserProcessCollector

    for fault in (False, True):
        collector = ProcessCapture(fault)
        assert isinstance(collector, BrowserProcessCollector)
        assert collector.page is None and collector.responses == []
        collector.before_action(guard())
        collector.sealed = True
        with pytest.raises(ValueError, match="sealed"):
            collector.before_action(guard())
        collector.close(guard())
        assert collector.close_calls == 1


@pytest.mark.parametrize("fault", [False, True])
def test_actual_browser_unique_returns_with_process_capture(
    monkeypatch: pytest.MonkeyPatch, fault: bool
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><title>Process fixture</title><p>Read-only fixture</p></html>"
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    frozen = spec(f"http://127.0.0.1:{server.server_port}/")
    process = ProcessCapture(fault)
    engine = BrowserGymEngine(
        frozen,
        LoopbackAuthority(),
        SystemClock(),
        NavigatePublicTask(),
        process_collector=process,
    )
    original = operation(frozen, "start")
    primary: BaseException | None = None
    try:
        initial = engine.start(original, control=guard(90))
        assert process.readouts == [initial] and initial.observation.sequence == 0
        done = BrowserAction(
            action_id="done",
            protocol_id="browsergym-highlevel-v1",
            name="send_msg_to_user",
            payload="send_msg_to_user('done')",
        )
        if fault:
            with pytest.raises(OSError, match="after actual return"):
                engine.step(done, operation(frozen, "done"), control=guard(30))
            assert engine.state == "quarantined"
        else:
            returned = engine.step(done, operation(frozen, "done"), control=guard(30))
            assert engine.state == "terminal" and returned is engine.last_readout
        assert engine.last_readout is process.readouts[-1]
        assert [r.observation.sequence for r in process.readouts] == [0, 1]
        assert process.readouts[-1].action == done and requests.count("/") == 1
        from lab_generate_skill.domain.errors import InvalidTransition

        with pytest.raises(InvalidTransition):
            engine.step(done, operation(frozen, "never-replay"), control=guard(30))
        assert len(process.readouts) == 2 and engine.sequence == 1
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            cleanup = original.cleanup(
                "close", now=datetime.now(timezone.utc), seconds=30
            )
            engine.close(cleanup, control=guard(30))
            engine.close(cleanup, control=guard(30))
            assert (
                engine.state == "closed"
                and engine.driver is None
                and process.close_calls == 1
                and process.page is None
            )
        except BaseException as error:
            if primary is not None:
                raise BaseExceptionGroup("Original and cleanup", [primary, error])
            raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
