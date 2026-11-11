"""Actual controlled native read -> retained full response, no browser/server relay."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import pytest
from lab_generate_skill.sites.map.native_exchange import NativeExchange
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.release import ReleaseFile
from map_artifact_fixtures import case
from map_http_fixtures import http_fixture
from map_xml_fixtures import ROOT
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "mode,status,adapted,calls",
    [
        ("normal", 200, False, 1),
        ("batch", 200, True, 3),
        ("cap", 400, False, 1),
        ("redirect", 302, False, 1),
    ],
)
def test_original_exchange_retained_before_result(
    tmp_path: Path, mode: str, status: int, adapted: bool, calls: int
) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with http_fixture(mode) as server:
        exchange = NativeExchange(
            "request-0", server.origin, ROOT, time.monotonic() + 10, writer, guard(30)
        )
        result = exchange.run()
        assert result.response.status == status and result.adapted is adapted
        assert len(server.calls) == calls
        with pytest.raises(InvalidTransition):
            exchange.run()
        assert len(server.calls) == calls
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert reader.read(handle, result.payload.path, guard()) == result.response.body
    manifest = reader.manifest(handle, guard())
    events = [
        json.loads(reader.read(handle, f.path, guard()))
        for f in manifest.artifact.files
        if f.path.endswith(".json")
    ]
    assert events[0]["source_record"]["status"] == "started"
    assert events[0]["body"] is None and exchange.state == "complete"
    assert all(c.cancelled.is_set() and c.connection is None for c in exchange.clients)


@pytest.mark.parametrize("mode", ["partial", "body"])
def test_failed_or_cancelled_exchange_preserves_partial_no_retry(
    tmp_path: Path, mode: str
) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    with http_fixture(mode) as server:
        exchange = NativeExchange(
            "request-0", server.origin, ROOT, time.monotonic() + 5, writer, guard(30)
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(exchange.run)
            if mode == "body":
                assert server.waiting.wait(2)
                exchange.cancel()
            with pytest.raises(IOError):
                future.result(timeout=3)
        assert len(server.calls) == 1 and exchange.state == "failed"
        assert exchange.records.rows[0]["body_complete"] is False
        retained = [
            (writer.working / f.path).read_bytes()
            for f in writer.files
            if f.path.endswith(".bin")
        ]
        assert retained and all(b"prefix".startswith(body) for body in retained)
        if mode == "partial":
            assert retained == [b"prefix"]
        with pytest.raises(InvalidTransition):
            exchange.run()


def test_intent_persistence_failure_prevents_http(tmp_path: Path) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    authority.denied = True
    with http_fixture() as server:
        exchange = NativeExchange(
            "request-0", server.origin, ROOT, time.monotonic() + 5, writer, guard()
        )
        with pytest.raises(PermissionError):
            exchange.run()
        assert not server.calls and exchange.state == "failed"
        with pytest.raises(InvalidTransition):
            exchange.run()


def test_response_file_failure_keeps_original_without_replay(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())

    class Sink:
        def retain(
            self, name: str, data: bytes, control: OperationControl
        ) -> ReleaseFile:
            if name.endswith("-response.bin"):
                raise OSError("response publish failed")
            return writer.retain(name, data, control)

    with http_fixture() as server:
        exchange = NativeExchange(
            "request-0", server.origin, ROOT, time.monotonic() + 5, Sink(), guard()
        )
        with pytest.raises(OSError, match="publish failed"):
            exchange.run()
        assert (
            exchange.original is exchange.pending_response
            and exchange.original is not None
        )
        assert len(server.calls) == 1 and exchange.result is None
        with pytest.raises(InvalidTransition):
            exchange.run()


def test_cancel_before_dispatch_and_competing_call(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    with http_fixture() as server:
        exchange = NativeExchange(
            "request-0", server.origin, ROOT, time.monotonic() + 5, writer, guard()
        )
        exchange.cancel()
        exchange.cancel()
        with pytest.raises(TimeoutError):
            exchange.run()
        assert not server.calls and not writer.files
    # A distinct new exchange in this independent fixture owns the sole call.
    with http_fixture("headers") as server:
        exchange = NativeExchange(
            "request-1", server.origin, ROOT, time.monotonic() + 5, writer, guard()
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(exchange.run)
            assert server.waiting.wait(2)
            with pytest.raises(InvalidTransition):
                exchange.run()
            server.release.set()
            assert future.result(timeout=3).response.status == 200
        assert len(server.calls) == 1


@pytest.mark.parametrize("deadline", [True, float("nan"), float("inf"), 0, -1])
def test_bad_original_deadline_no_effects(tmp_path: Path, deadline: float) -> None:
    writer, _ = case(tmp_path)
    with pytest.raises(ValueError):
        NativeExchange(
            "request-0", "http://127.0.0.1:1", ROOT, deadline, writer, guard()
        )
    assert not writer.root.exists()


@pytest.mark.parametrize("name", ["", "UPPER", "a" * 27, "a/b", "a b"])
def test_invalid_request_identity_no_effects(tmp_path: Path, name: str) -> None:
    writer, _ = case(tmp_path)
    with pytest.raises(ValueError):
        NativeExchange(
            name, "http://127.0.0.1:1", ROOT, time.monotonic() + 5, writer, guard()
        )
    assert not writer.root.exists()


def test_read_and_failure_retention_errors_both_preserved(tmp_path: Path) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())

    class Sink:
        def retain(
            self, name: str, data: bytes, control: OperationControl
        ) -> ReleaseFile:
            if name.endswith("0001.bin"):
                raise OSError("partial retention failed")
            return writer.retain(name, data, control)

    with http_fixture("partial") as server:
        exchange = NativeExchange(
            "request-0", server.origin, ROOT, time.monotonic() + 5, Sink(), guard()
        )
        with pytest.raises(BaseExceptionGroup) as caught:
            exchange.run()
        assert len(caught.value.exceptions) == 2
        assert "partial retention" in str(caught.value.exceptions[1])
        assert (
            exchange.records.pending_payloads[0] == b"prefix" and len(server.calls) == 1
        )
        with pytest.raises(InvalidTransition):
            exchange.run()
