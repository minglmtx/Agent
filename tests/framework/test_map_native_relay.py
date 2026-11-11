"""Actual two HTTP hops + retained files; no Map service or browser provenance."""

from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import socket
import time
from urllib.parse import urlsplit
import pytest
from lab_generate_skill.sites.map.native_relay import NativeMapRelay
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import InvalidTransition
from map_artifact_fixtures import case
from map_http_fixtures import http_fixture
from map_xml_fixtures import ROOT
from test_slurm_commands import guard


def get(url: str, origin: str | None = None) -> tuple[int, bytes, str | None]:
    parsed = urlsplit(url)
    assert parsed.hostname is not None
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        connection.request(
            "GET", parsed.path, headers={} if origin is None else {"Origin": origin}
        )
        response = connection.getresponse()
        return (
            response.status,
            response.read(),
            response.getheader("Access-Control-Allow-Origin"),
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    "mode,expected,native_calls",
    [("normal", 200, 1), ("batch", 200, 3), ("cap", 400, 1), ("redirect", 302, 1)],
)
def test_actual_relay_retains_delivers_once_and_closes(
    tmp_path: Path, mode: str, expected: int, native_calls: int
) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with http_fixture(mode) as server:
        relay = NativeMapRelay(server.origin, writer, guard(60), max_requests=2)
        relay.start(guard())
        try:
            url = relay.register("request-0", ROOT, time.monotonic() + 15, guard())
            assert not server.calls
            status, body, allowed = get(url, server.origin)
            assert status == expected and allowed == server.origin
            assert len(server.calls) == native_calls
            assert get(url)[0] == 410 and len(server.calls) == native_calls
            with pytest.raises(InvalidTransition):
                relay.register("request-0", ROOT, time.monotonic() + 10, guard())
        finally:
            relay.close(guard())
        relay.close(guard())
        assert relay.physical_closed and relay.state == "closed"
        assert not relay.handler_sockets and all(
            not t.is_alive() for t in relay.handler_threads
        )
        job = next(iter(relay.requests.values()))
        assert job.finished and job.delivery_complete and not job.errors
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert reader.read(handle, "request-0-response.bin", guard()) == body
    end = json.loads(reader.read(handle, "request-0-delivery-end.json", guard()))
    assert (
        end["delivered_bytes"] == len(body)
        and end["delivery_complete"]
        and not end["errors"]
    )


def test_relay_wrong_origin_and_path_do_not_consume_original(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    with http_fixture() as server:
        relay = NativeMapRelay(server.origin, writer, guard(), max_requests=1)
        relay.start(guard())
        try:
            url = relay.register("request-0", ROOT, time.monotonic() + 10, guard())
            assert get(url, "http://127.0.0.1:1")[0] == 403
            assert get(url + "-unknown")[0] == 404
            assert not server.calls
            assert get(url)[0] == 200 and len(server.calls) == 1
            with pytest.raises(ValueError):
                relay.register("request-1", ROOT, time.monotonic() + 10, guard())
        finally:
            relay.close(guard())


def test_relay_close_without_browser_request_and_partial_headers(
    tmp_path: Path,
) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    with http_fixture() as server:
        relay = NativeMapRelay(server.origin, writer, guard(), max_requests=1)
        relay.start(guard())
        url = relay.register("request-0", ROOT, time.monotonic() + 10, guard())
        parsed = urlsplit(url)
        assert parsed.hostname is not None and parsed.port is not None
        connection = socket.create_connection((parsed.hostname, parsed.port), timeout=2)
        try:
            connection.sendall(b"GET /incomplete HTTP/1.1\r\n")
            deadline = time.monotonic() + 2
            while not relay.handler_threads and time.monotonic() < deadline:
                time.sleep(0.01)
            assert relay.handler_threads
            relay.close(guard())
            assert (
                relay.physical_closed and not server.calls and not relay.handler_sockets
            )
        finally:
            connection.close()
            relay.close(guard())
        row = json.loads(
            (writer.working / "request-0-never-requested.json").read_text()
        )
        assert row["status"] == "unknown" and row["native_dispatches"] == 0
        with pytest.raises(InvalidTransition):
            relay.register("request-1", ROOT, time.monotonic() + 10, guard())


def test_relay_partial_body_keeps_unknown_and_no_native_replay(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    with http_fixture("partial") as server:
        relay = NativeMapRelay(server.origin, writer, guard(), max_requests=1)
        relay.start(guard())
        try:
            url = relay.register("request-0", ROOT, time.monotonic() + 10, guard())
            assert get(url)[0] == 502
            assert get(url)[0] == 410 and len(server.calls) == 1
        finally:
            relay.close(guard())
        job = next(iter(relay.requests.values()))
        assert (
            job.finished
            and job.errors
            and not job.delivery_complete
            and relay.physical_closed
        )
        assert job.exchange.records.rows[0]["body_complete"] is False
        assert (
            writer.working / "request-0-first-event-0001.bin"
        ).read_bytes() == b"prefix"


def test_relay_cancel_original_reader_closes_all_owned_threads(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    with http_fixture("body") as server:
        relay = NativeMapRelay(server.origin, writer, guard(30), max_requests=1)
        relay.start(guard())
        url = relay.register("request-0", ROOT, time.monotonic() + 10, guard())
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(get, url)
            assert server.waiting.wait(2)
            relay.close(guard())
            with pytest.raises((http.client.RemoteDisconnected, ConnectionResetError)):
                future.result(timeout=3)
        assert (
            relay.physical_closed
            and not relay.handler_sockets
            and len(server.calls) == 1
        )
        job = next(iter(relay.requests.values()))
        assert job.errors and job.finished and not job.delivery_complete


def test_relay_failed_registration_never_dispatches(tmp_path: Path) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with http_fixture() as server:
        relay = NativeMapRelay(server.origin, writer, guard(), max_requests=1)
        relay.start(guard())
        authority.denied = True
        with pytest.raises(PermissionError):
            relay.register("request-0", ROOT, time.monotonic() + 10, guard())
        with pytest.raises(InvalidTransition):
            relay.register("request-0", ROOT, time.monotonic() + 10, guard())
        relay.close(guard())
        assert (
            relay.registration_error is not None
            and not server.calls
            and relay.physical_closed
        )


@pytest.mark.parametrize("count", [False, 0, -1, 257])
def test_relay_invalid_capacity_before_side_effects(tmp_path: Path, count: int) -> None:
    writer, _ = case(tmp_path)
    with pytest.raises(ValueError):
        NativeMapRelay("http://127.0.0.1:1", writer, guard(), max_requests=count)
    assert not writer.root.exists()


def test_relay_non_tcp_input_rejected_before_handler_creation(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    relay = NativeMapRelay("http://127.0.0.1:1", writer, guard(), max_requests=1)
    relay.start(guard())
    try:
        assert relay.server is not None
        with socket.socket() as connection:
            for method in (
                relay.server.process_request,
                relay.server.process_request_thread,
            ):
                with pytest.raises(TypeError, match="TCP socket"):
                    method((b"unexpected-udp", connection), ("127.0.0.1", 1))
        assert not relay.handler_threads and not relay.requests
    finally:
        relay.close(guard())
    assert relay.physical_closed
