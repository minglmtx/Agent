"""Actual BrowserGym/XHR/relay/complete files, on a controlled HTTP fixture only."""

from contextlib import contextmanager
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from typing import Iterator
from urllib.parse import parse_qs, urlsplit
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.browser_process import BrowserProcessCollector
from lab_generate_skill.sites.map.native_route_collector import (
    MapNativeRequestCollector,
)
from lab_generate_skill.sites.map.native_relay import NativeMapRelay
from browsergym_fixtures import operation, LoopbackAuthority, CHROMIUM
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec
from map_xml_fixtures import ROOT, xml
from test_slurm_commands import guard

SCRIPT = """
window.jQuery = {active: 0};
window.actualXHRs = 0;
document.getElementById('native').onclick = () => {
  window.actualXHRs += 1;
  jQuery.active += 1;
  const xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/0.6/map?bbox=0,0,0.5,0.5');
  xhr.onload = () => {
    window.nativeStatus = xhr.status;
    window.nativeBody = xhr.responseText;
    document.getElementById('result').textContent = 'Native response received';
    jQuery.active -= 1;
  };
  xhr.onerror = () => { window.nativeError = true; jQuery.active -= 1; };
  xhr.send();
};
document.cookie = 'fixture_private=do-not-forward; path=/';
"""
HTML = (
    '<html><title>Controlled MapData</title><button id="native">Fetch Map Data</button><p id="result">No request yet</p><script>'
    + SCRIPT
    + "</script></html>"
).encode()


@dataclass
class Fixture:
    origin: str = ""
    native_calls: list[tuple[tuple[str, ...], dict[str, str]]] = field(
        default_factory=list
    )
    documents: int = 0
    note_calls: int = 0


@contextmanager
def server_fixture(
    mode: str,
    *,
    document: bytes = HTML,
    assets: Mapping[str, bytes] | None = None,
    incomplete_assets: frozenset[str] = frozenset(),
    document_target: str | None = None,
) -> Iterator[Fixture]:
    if mode not in ("normal", "batch"):
        raise ValueError("Explicit controlled native fixture mode required")
    fixture = Fixture()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if (
                self.path == document_target
                if document_target is not None
                else parsed.path == "/"
            ):
                fixture.documents += 1
                status, body, content_type = 200, document, "text/html; charset=utf-8"
            elif assets is not None and parsed.path in assets:
                status, body, content_type = (
                    200,
                    assets[parsed.path],
                    "application/javascript; charset=utf-8",
                )
                if parsed.path == "/api/0.6/notes.json":
                    fixture.note_calls += 1
                    content_type = "application/json"
            elif parsed.path == "/api/0.6/map":
                bounds = tuple(parse_qs(parsed.query)["bbox"][0].split(","))
                fixture.native_calls.append(
                    (bounds, {k.lower(): v for k, v in self.headers.items()})
                )
                status, body, content_type = (
                    200,
                    xml(bounds),
                    "application/xml; charset=utf-8",
                )
                if mode == "batch" and bounds == ROOT:
                    status = 400
                    body = b"You requested too many nodes (limit is 50000). Either request a smaller area, or use planet.osm\n"
            else:
                status, body, content_type = 404, b"", "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Content-Length",
                str(len(body) + (17 if parsed.path in incomplete_assets else 0)),
            )
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fixture.origin = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield fixture
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_actual_map_route_fixture_preflight(tmp_path: Path) -> None:
    import playwright

    node = Path(playwright.__file__).parent / "driver/node"
    completed = subprocess.run(
        [str(node), "--check"],
        input=SCRIPT.encode(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    writer, _ = case(tmp_path)
    frozen = selected_spec(writer, "http://127.0.0.1:1/")
    relay = NativeMapRelay("http://127.0.0.1:1", writer, guard(), max_requests=4)
    collector = MapNativeRequestCollector(writer.plan, relay)
    assert (
        isinstance(collector, BrowserProcessCollector)
        and frozen.scope == writer.plan.scope
    )
    assert not writer.root.exists() and relay.server is None
    for mode in ("normal", "batch"):
        with server_fixture(mode) as fixture:
            assert not fixture.native_calls and fixture.documents == 0


@pytest.mark.parametrize(
    "mode,ending", [("normal", "protocol"), ("batch", "protocol"), ("batch", "limit")]
)
def test_actual_browser_map_route_unique_returns_and_closed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, ending: str
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with server_fixture(mode) as fixture:
        frozen = selected_spec(writer, fixture.origin + "/")
        relay = NativeMapRelay(fixture.origin, writer, guard(180), max_requests=4)
        collector = MapNativeRequestCollector(writer.plan, relay)
        engine = BrowserGymEngine(
            frozen,
            LoopbackAuthority(),
            SystemClock(),
            NavigatePublicTask(),
            process_collector=collector,
        )
        original = operation(frozen, "start")
        primary: BaseException | None = None
        try:
            initial = engine.start(original, control=guard(90))
            assert collector.readouts == [initial] and collector.last_readout is initial
            assert not fixture.native_calls
            text = initial.observation.text
            assert text is not None
            button = re.search(r"\[([^\]]+)\] button [\'\"]Fetch Map Data[\'\"]", text)
            assert button, text
            clicked = engine.step(
                BrowserAction(
                    action_id="native",
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload=f"click({button.group(1)!r})",
                ),
                operation(frozen, "click"),
                control=guard(30),
            )
            assert collector.last_readout is clicked and collector.readouts == [
                initial,
                clicked,
            ]
            if ending == "protocol":
                final = engine.step(
                    BrowserAction(
                        action_id="finish",
                        protocol_id="browsergym-highlevel-v1",
                        name="send_msg_to_user",
                        payload="send_msg_to_user('done')",
                    ),
                    operation(frozen, "finish"),
                    control=guard(30),
                )
                assert collector.last_readout is final and engine.last_readout is final
                assert collector.state == "terminal_pending"
                assert collector.finish_record is None
            collector.finish(guard(30))
            assert (
                collector.state == "terminal"
                and collector.finish_record is not None
                and collector.finish_record["passed"]
            )
            body = engine.env.page.evaluate("window.nativeBody")
            assert (
                isinstance(body, str)
                and engine.env.page.evaluate("window.nativeStatus") == 200
            )
            assert (
                engine.env.page.evaluate("window.actualXHRs") == 1
                and fixture.documents == 1
            )
            assert len(fixture.native_calls) == (3 if mode == "batch" else 1)
            assert sum(bounds == ROOT for bounds, _ in fixture.native_calls) == 1
            assert all(
                "cookie" not in headers and "authorization" not in headers
                for _, headers in fixture.native_calls
            )
            count = len(collector.readouts)
            with pytest.raises(InvalidTransition):
                engine.step(
                    BrowserAction(
                        action_id="never-again",
                        protocol_id="browsergym-highlevel-v1",
                        name="click",
                        payload=f"click({button.group(1)!r})",
                    ),
                    operation(frozen, "never-again"),
                    control=guard(),
                )
            assert len(collector.readouts) == count and [
                r.observation.sequence for r in collector.readouts
            ] == list(range(count))
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                cleanup = original.cleanup(
                    "close", now=datetime.now(timezone.utc), seconds=30
                )
                engine.close(cleanup, control=guard(30))
                assert (
                    relay.physical_closed
                    and collector.state == "closed"
                    and not relay.handler_sockets
                )
                assert engine.driver is None and engine.state == "closed"
            except BaseException as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Original browser route test and cleanup", [primary, error]
                    )
                raise
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert reader.read(handle, "request-0-response.bin", guard()) == body.encode()
    request = json.loads(reader.read(handle, "request-0-browser-start.json", guard()))
    assert request["resource_type"] == "xhr" and request["method"] == "GET"
    assert request["last_unique_observation_sequence"] == 0 and request[
        "requested_bbox_strings"
    ] == list(ROOT)
    for readout in collector.readouts:
        stored = json.loads(
            reader.read(
                handle, f"map-observation-{readout.observation.sequence}.json", guard()
            )
        )
        assert stored["readout"] == readout.model_dump(mode="json")
