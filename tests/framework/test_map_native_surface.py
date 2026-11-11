"""Full passive reads, original capsule parity and the existing process seam."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.ports.browser_process import BrowserProcessCollector
from lab_generate_skill.sites.map.native_surface_capture import NativeSurfaceCapture
from lab_generate_skill.sites.map.native_surface_script import (
    READ,
    NOTE_MARKERS_READ,
    ROUTE_READ,
    COMBINED_READ,
)
from lab_generate_skill.sites.map.native_process_collector import (
    MapNativeProcessCollector,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from map_artifact_fixtures import case
from map_database_original_oracle import W, ROOT, CAPSULE
from map_route_fixtures import Page, Route, collection, readout, selected_spec
from map_http_fixtures import http_fixture
from test_map_native_relay import get
from test_slurm_commands import guard


class SurfacePage(Page):
    def __init__(self, value: Any = None) -> None:
        super().__init__()
        self.value = {"surface": {}, "route": {}} if value is None else value
        self.reads = 0
        self.error: BaseException | None = None

    def evaluate(self, expression: str) -> Any:
        assert expression == COMBINED_READ
        self.reads += 1
        if self.error is not None:
            raise self.error
        return self.value


def test_original_passive_reader_literals_and_javascript_preflight() -> None:
    import playwright

    raw = CAPSULE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "3c537fffffcf2768fc3bcedb4e567ed39565f76faf01f3b1f685614d35e724f5"
    )
    pins = json.loads(raw)["members"]
    for module, name, current in (
        ("map_local_surface_controls", "READ", READ),
        ("map_native_layer_completion", "NOTE_MARKERS_READ", NOTE_MARKERS_READ),
        ("map_route", "read_route", ROUTE_READ),
    ):
        rel = f"src/lab_generate_skill/{module}.py"
        source = (ROOT / rel).read_bytes()
        assert hashlib.sha256(source).hexdigest() == pins[rel]["sha256"]
        tree = ast.parse(source)
        if name == "read_route":
            fn = next(
                n
                for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == name
            )
            statement = fn.body[0]
            assert isinstance(statement, ast.Return) and isinstance(
                statement.value, ast.Call
            )
            original = ast.literal_eval(statement.value.args[0])
        else:
            assignment = next(
                n
                for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
            )
            original = ast.literal_eval(assignment.value)
        assert current == original
    result = subprocess.run(
        [str(Path(playwright.__file__).parent / "driver/node"), "--check"],
        input=("const read = " + COMBINED_READ + ";").encode(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_full_surface_preserved_with_original_readout_and_terminal(
    tmp_path: Path,
) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    page = SurfacePage(
        {
            "surface": {"rendered_paths": [{"d": "M" + "1 " * 10000}] * 101},
            "route": {"rows": [str(i) for i in range(1001)]},
        }
    )
    c = NativeSurfaceCapture(writer.plan, writer, guard())
    c.bind(page)
    initial = readout(selected_spec(writer, "http://127.0.0.1:1/"), 0)
    first = c.capture(page, initial, guard(), phase="unique_return")
    final = c.capture(page, initial, guard(), phase="terminal")
    assert c.last_readout is initial and page.reads == 2 and c.pending_record is None
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    for artifact in (first, final):
        stored = json.loads(reader.read(handle, artifact.path, guard()))
        assert stored["facts"] == page.value
        assert stored["original_readout"] == initial.model_dump(mode="json")
        assert stored["new_action_or_observation"] is False
    with pytest.raises(InvalidTransition):
        c.capture(page, initial, guard(), phase="terminal")
    assert page.reads == 2


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        "",
        1,
        {},
        {"surface": [], "route": {}},
        {"surface": {}, "route": {}, "extra": 0},
    ],
)
def test_invalid_envelope_retained_then_quarantined(tmp_path: Path, bad: Any) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    page = SurfacePage()
    page.value = bad
    c = NativeSurfaceCapture(writer.plan, writer, guard())
    c.bind(page)
    original = readout(selected_spec(writer, "http://127.0.0.1:1/"), 0)
    with pytest.raises(ValueError, match="envelope"):
        c.capture(page, original, guard(), phase="unique_return")
    assert len(c.records) == 1 and c.pending_record is not None
    assert c.pending_record["facts"] == bad
    with pytest.raises(EvidenceIntegrityError):
        c.capture(page, original, guard(), phase="unique_return")
    assert page.reads == 1


@pytest.mark.parametrize(
    "fault", ["read", "write", "expired", "identity", "sequence", "phase", "type"]
)
def test_surface_failure_no_replay(tmp_path: Path, fault: str) -> None:
    writer, _ = case(tmp_path)
    writer.initialize(guard())
    page = SurfacePage()
    c = NativeSurfaceCapture(writer.plan, writer, guard())
    c.bind(page)
    original: Any = readout(
        selected_spec(writer, "http://127.0.0.1:1/"), int(fault == "sequence")
    )
    control = guard()
    phase: Any = "unique_return"
    target = page
    error: type[BaseException] = OSError
    if fault == "read":
        page.error = OSError("original page evaluation failed")
    elif fault == "write":

        class FailedSink:
            def retain(self, *args: Any) -> Any:
                raise OSError("original write result unknown")

        c.sink = FailedSink()
    elif fault == "expired":
        control = guard(-1)
        error = OperationStopped
    elif fault == "identity":
        target = SurfacePage()
        error = OwnershipConflict
    elif fault == "sequence":
        error = InvalidTransition
    elif fault == "phase":
        phase = "other"
        error = ValueError
    elif fault == "type":
        original = {}
        error = TypeError
    with pytest.raises(error):
        c.capture(target, original, control, phase=phase)
    assert page.reads == (1 if fault in ("read", "write") else 0)
    if fault == "write":
        assert c.pending_record is not None and c.pending_record["facts"] == page.value
    with pytest.raises(EvidenceIntegrityError):
        c.capture(page, original, guard(), phase="unique_return")


@pytest.mark.parametrize("ending", ["protocol", "limit", "surface_failure"])
def test_composed_surface_transport_and_close(tmp_path: Path, ending: str) -> None:
    with http_fixture("batch") as server:
        requests, writer, authority, _, spec = collection(tmp_path, server.origin)
        page = SurfacePage()
        c = MapNativeProcessCollector(requests)
        assert isinstance(c, BrowserProcessCollector)
        c.attach(page, spec, guard())
        try:
            initial = readout(spec, 0)
            c.observe(page, initial, guard())
            route = Route(server.origin)
            page.handler(route)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get, route.calls[0]["url"], server.origin)
                if ending == "surface_failure":
                    page.error = OSError("surface failure after actual browser return")
                    with pytest.raises(OSError):
                        c.observe(page, readout(spec, 1), guard())
                    with pytest.raises(EvidenceIntegrityError):
                        c.before_action(guard())
                else:
                    c.observe(
                        page, readout(spec, 1, terminal=ending == "protocol"), guard()
                    )
                    c.finish(guard())
                    count = page.reads
                    c.finish(guard())
                    assert page.reads == count == 3
                    assert c.final_captured
                assert future.result(timeout=10)[0] == 200
        finally:
            c.close(guard())
        assert requests.relay.physical_closed and requests.state == "closed"
        assert (
            len(requests.readouts) == 2
            and c.surface.last_readout is requests.last_readout
        )
        c.close(guard())
        with pytest.raises(InvalidTransition):
            c.before_action(guard())
        handle = writer.seal(guard())
        close = json.loads(
            MapArtifactReader(writer.plan, tmp_path, authority).read(
                handle, "map-page-close.json", guard()
            )
        )
        assert bool(close["errors"]) == (ending == "surface_failure")
        if ending == "surface_failure":
            assert "surface failure after actual browser return" in close["errors"][0]
        assert close["unique_return_count"] == 2


def test_surface_close_unknown_never_retried_and_transport_closed(
    tmp_path: Path,
) -> None:
    requests, writer, _, _, spec = collection(tmp_path, "http://127.0.0.1:1")
    page = SurfacePage()
    collector = MapNativeProcessCollector(requests)
    collector.attach(page, spec, guard())
    collector.observe(page, readout(spec, 0), guard())

    class UnknownClose:
        calls = 0

        def retain(self, *args: Any) -> Any:
            self.calls += 1
            raise OSError("surface closure write result unknown")

    sink = UnknownClose()
    collector.surface.sink = sink
    for _ in range(2):
        with pytest.raises(BaseExceptionGroup) as error:
            collector.close(guard())
        assert "surface closure write result unknown" in str(
            collector.surface.cleanup_errors[0]
        )
        assert len(error.value.exceptions) == 1
        assert requests.relay.physical_closed and requests.state == "closed"
    assert sink.calls == 1


def test_foreign_thread_close_cannot_mutate_original_process(tmp_path: Path) -> None:
    requests, _, _, _, spec = collection(tmp_path, "http://127.0.0.1:1")
    page = SurfacePage()
    collector = MapNativeProcessCollector(requests)
    collector.attach(page, spec, guard())
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(collector.close, guard())
            with pytest.raises(OwnershipConflict):
                future.result(timeout=3)
        assert not collector.closed and not collector.surface.close_attempted
        assert requests.state == "active" and not requests.relay.physical_closed
        collector.before_action(guard())
        collector.observe(page, readout(spec, 0), guard())
    finally:
        collector.close(guard())
    assert collector.closed and requests.relay.physical_closed


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_stop_after_page_read_keeps_complete_original_facts(
    tmp_path: Path, reason: str
) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    page = SurfacePage(
        {"surface": {"complete": "original"}, "route": {"rows": ["original"]}}
    )
    c = NativeSurfaceCapture(writer.plan, writer, guard())
    c.bind(page)
    original = readout(selected_spec(writer, "http://127.0.0.1:1/"), 0)

    class StopAfterRead:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if self.calls == 2:
                raise OperationStopped(reason, "original-surface-read")
            return 10.0

        def wait(self, seconds: float) -> None:
            raise AssertionError("Passive reader must not wait")

    with pytest.raises(OperationStopped) as error:
        c.capture(page, original, StopAfterRead(), phase="unique_return")
    assert error.value.reason_code == reason and page.reads == 1
    assert c.pending_record is not None and len(c.records) == 1
    c.close(guard())
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert (
        json.loads(reader.read(handle, c.records[0].path, guard()))["facts"]
        == page.value
    )
    closed = json.loads(reader.read(handle, "map-page-close.json", guard()))
    assert reason in closed["errors"][0] and closed["pending_record_retained"]
