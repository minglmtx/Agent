"""Terminal action delivery precedes explicit settling of the original request.

Controlled HTTP, original collector and full files; no production Map request,
Actor replay, database or task verdict is exercised here.
"""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OperationStopped,
)
from map_http_fixtures import http_fixture
from map_route_fixtures import Route, collection, readout
from test_map_native_relay import get
from test_slurm_commands import guard


@pytest.mark.parametrize("ending", ["protocol_terminal", "terminated", "truncated"])
def test_terminal_return_does_not_wait_for_original_pending_http(
    tmp_path: Path, ending: str
) -> None:
    with http_fixture("headers") as server:
        c, writer, _, page, spec = collection(tmp_path, server.origin)
        c.attach(page, spec, guard())
        try:
            c.observe(page, readout(spec, 0), guard())
            route = Route(server.origin)
            page.handler(route)
            job = next(iter(c.relay.requests.values()))
            assert job.exchange.request_id == "request-0"
            deadline = job.exchange.deadline
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get, route.calls[0]["url"], server.origin)
                try:
                    assert server.waiting.wait(1) and not future.done()
                    original = readout(spec, 1, terminal=ending == "protocol_terminal")
                    if ending != "protocol_terminal":
                        original = original.model_copy(update={ending: True})
                    c.observe(page, original, guard(0.2))
                    assert not future.done() and not job.finished
                    assert c.last_readout is original and c.state == "terminal_pending"
                    assert c.finish_record is None and page.renderer_waits == 0
                    assert job.exchange.deadline == deadline and len(server.calls) == 1
                    with pytest.raises(InvalidTransition):
                        c.before_action(guard())
                    with pytest.raises(InvalidTransition):
                        c.observe(page, original, guard())
                    assert c.state == "terminal_pending" and len(c.readouts) == 2
                finally:
                    server.release.set()
                c.finish(guard(5))
                assert future.result(timeout=2)[0] == 200
            assert c.state == "terminal" and job.delivery_complete
            assert job.exchange.deadline == deadline and len(server.calls) == 1
            retained = json.loads(
                (writer.working / "map-observation-1.json").read_text()
            )
            assert retained["readout"] == original.model_dump(mode="json")
            assert c.finish_record is not None and c.finish_record["passed"]
            c.finish(guard())
            assert len(server.calls) == 1 and page.renderer_waits == 1
        finally:
            server.release.set()
            c.close(guard())
        assert c.relay.physical_closed


class CancelDuringSettle:
    """Cancel after finish entered; the original request is never dispatched."""

    def __init__(self) -> None:
        self.calls = 0

    def checkpoint(self) -> float:
        self.calls += 1
        if self.calls > 1:
            raise OperationStopped("CANCELLED", "terminal-capture")
        return 5.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


def test_terminal_capture_cancel_keeps_failed_state_and_no_dispatch(
    tmp_path: Path,
) -> None:
    c, writer, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    c.observe(page, readout(spec, 0), guard())
    page.handler(Route(c.relay.origin))
    c.observe(page, readout(spec, 1, terminal=True), guard())
    try:
        with pytest.raises(OperationStopped) as stopped:
            c.finish(CancelDuringSettle())
        assert stopped.value.reason_code == "CANCELLED" and c.state == "failed"
        assert not next(iter(c.relay.requests.values())).started
        retained = json.loads(
            (writer.working / "map-existing-pending-finish.json").read_text()
        )
        assert not retained["passed"] and not retained["new_requests_created"]
        with pytest.raises(InvalidTransition):
            c.finish(guard())
    finally:
        c.close(guard())
    assert c.relay.physical_closed


def test_new_callback_after_terminal_return_is_rejected_without_dispatch(
    tmp_path: Path,
) -> None:
    c, _, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    c.observe(page, readout(spec, 0), guard())
    c.observe(page, readout(spec, 1, terminal=True), guard())
    route = Route(c.relay.origin)
    page.handler(route)
    try:
        assert route.aborts == 1 and not route.calls and not c.relay.requests
        assert c.state == "failed" and c.errors
        with pytest.raises(InvalidTransition):
            c.finish(guard())
    finally:
        c.close(guard())
    assert c.relay.physical_closed


def test_terminal_capture_keeps_partial_response_unknown(tmp_path: Path) -> None:
    with http_fixture("body") as server:
        c, writer, _, page, spec = collection(tmp_path, server.origin)
        c.attach(page, spec, guard())
        try:
            c.observe(page, readout(spec, 0), guard())
            route = Route(server.origin)
            page.handler(route)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get, route.calls[0]["url"], server.origin)
                try:
                    assert server.waiting.wait(1)
                    c.observe(page, readout(spec, 1, terminal=True), guard())
                    assert c.state == "terminal_pending" and not future.done()
                finally:
                    server.release.set()
                assert future.result(timeout=3)[0] == 502
                with pytest.raises(EvidenceIntegrityError):
                    c.finish(guard())
            assert c.state == "failed" and len(server.calls) == 1
            assert not next(iter(c.relay.requests.values())).delivery_complete
            assert (
                writer.working / "request-0-first-event-0001.bin"
            ).read_bytes() == b"prefix"
            with pytest.raises(InvalidTransition):
                c.finish(guard())
        finally:
            server.release.set()
            c.close(guard())
        assert c.relay.physical_closed
