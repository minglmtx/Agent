"""Current MapData Notes capture/fault branch and original process composition."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.sites.map.native_notes_capture import NativeNotesCapture
from lab_generate_skill.sites.map.native_process_collector import (
    MapNativeProcessCollector,
)
from map_database_original_oracle import ROOT, CAPSULE
from map_notes_fixtures import notes_case, NotesPage, NotesResponse, ORIGIN
from map_route_fixtures import collection, readout
from test_map_native_served_failures import FailedSink
from test_slurm_commands import guard


def test_original_selected_driver_capture_fault_precedes_layer_judgment() -> None:
    capsule = CAPSULE.read_bytes()
    assert (
        hashlib.sha256(capsule).hexdigest()
        == "3c537fffffcf2768fc3bcedb4e567ed39565f76faf01f3b1f685614d35e724f5"
    )
    rel = "src/lab_generate_skill/map_native_layer_runtime.py"
    source = (ROOT / rel).read_bytes()
    assert (
        hashlib.sha256(source).hexdigest()
        == json.loads(capsule)["members"][rel]["sha256"]
    )
    tree = ast.parse(source)
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "NativeLayerHooks"
    )
    fn = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "evaluate"
    )
    version = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets)
    )
    namespace: dict[str, Any] = {"VERSION": version}
    exec(
        compile(ast.Module(body=[fn], type_ignores=[]), str(ROOT / rel), "exec"),
        namespace,
    )
    # Only the exact early error branch is executed: no old service or runtime import.
    result = namespace["evaluate"](
        SimpleNamespace(faults=["original_notes_capture_error"], initial=None), None, {}
    )
    assert result["status"] == "unknown" and result["reward"] is None
    assert result["reason"] == "Native layer runtime or response capture incomplete"


@pytest.mark.parametrize(
    "body,status",
    [
        (b"", 200),
        (b"not-json", 200),
        (b"native unavailable", 503),
        (b"x" * (2 * 1024 * 1024), 200),
    ],
)
def test_complete_response_preserved_without_semantic_relabel(
    tmp_path: Path, body: bytes, status: int
) -> None:
    c, page, original, writer, authority = notes_case(tmp_path)
    response = NotesResponse(body)
    response.status = status
    page.listener(response)
    assert response.reads == 0
    c.observe(page, original, guard())
    c.observe(page, original, guard())
    assert c.last_readout is original and response.reads == 1 and len(c.records) == 1
    c.close(guard())
    c.close(guard())
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert reader.read(handle, "map-notes-0.bin", guard()) == body
    record = json.loads(reader.read(handle, "map-notes-0-end.json", guard()))
    assert record["http_status"] == status and record["complete"] is True
    assert record["unique_observation_sequence"] == 0
    closed = json.loads(reader.read(handle, "map-notes-close.json", guard()))
    assert closed["complete"] and not closed["task_success_or_admission_claim"]


@pytest.mark.parametrize("changed", ["origin", "path", "method", "type"])
def test_other_responses_unchanged(tmp_path: Path, changed: str) -> None:
    c, page, original, _, _ = notes_case(tmp_path)
    response = NotesResponse()
    if changed == "origin":
        response.url = response.url.replace(":1/", ":2/")
    if changed == "path":
        response.url = response.url.replace("notes.json", "map")
    if changed == "method":
        response.request.method = "POST"
    if changed == "type":
        response.request.resource_type = "fetch"
    page.listener(response)
    c.observe(page, original, guard())
    c.close(guard())
    assert not c.responses and response.reads == 0


@pytest.mark.parametrize(
    "fault", ["body", "wrong-type", "write", "record", "expired", "readout", "page"]
)
def test_capture_failure_never_retries_original_body(
    tmp_path: Path, fault: str
) -> None:
    c, page, original, writer, authority = notes_case(tmp_path)
    response = NotesResponse()
    if fault == "body":
        response.error = OSError("original Notes body reply unknown")
    if fault == "wrong-type":
        response.raw = None
    if fault in ("write", "record"):
        c.sink = FailedSink(
            writer, "map-notes-0.bin" if fault == "write" else "map-notes-0-end.json"
        )
    page.listener(response)
    with pytest.raises((OSError, OperationStopped, TypeError, OwnershipConflict)):
        c.observe(
            NotesPage() if fault == "page" else page,
            {} if fault == "readout" else original,
            guard(-1) if fault == "expired" else guard(),
        )
    if fault == "write":
        assert c.pending_body == response.raw
    reads = response.reads
    with pytest.raises(EvidenceIntegrityError):
        c.observe(page, original, guard())
    c.close(guard())
    assert response.reads == reads
    handle = writer.seal(guard())
    closed = json.loads(
        MapArtifactReader(writer.plan, tmp_path, authority).read(
            handle, "map-notes-close.json", guard()
        )
    )
    assert not closed["complete"] and closed["errors"]


@pytest.mark.parametrize("duplicate", [True, False])
def test_callback_duplicate_or_budget_refused(tmp_path: Path, duplicate: bool) -> None:
    c, page, original, _, _ = notes_case(tmp_path)
    responses = (
        [NotesResponse()] * 2 if duplicate else [NotesResponse() for _ in range(257)]
    )
    for response in responses:
        page.listener(response)
    with pytest.raises(EvidenceIntegrityError):
        c.observe(page, original, guard())
    c.close(guard())
    assert all(response.reads == 0 for response in responses)


def test_close_reads_only_known_pending_without_forging_return(tmp_path: Path) -> None:
    c, page, _, _, _ = notes_case(tmp_path)
    response = NotesResponse()
    page.listener(response)
    c.close(guard())
    c.close(guard())
    assert response.reads == 1 and page.listener is None
    assert (
        c.records[0]["unique_observation_sequence"] is None and c.records[0]["complete"]
    )


def test_foreign_owner_close_preserves_original(tmp_path: Path) -> None:
    c, _, _, _, _ = notes_case(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(OwnershipConflict):
            executor.submit(c.close, guard()).result(timeout=3)
    assert not c.close_attempted and c.state == "active"
    c.close(guard())


@pytest.mark.parametrize("fault", ["normal", "body", "attach", "detach"])
def test_composed_note_capture_and_resource_close(tmp_path: Path, fault: str) -> None:
    requests, writer, authority, _, spec = collection(tmp_path, ORIGIN)
    notes = NativeNotesCapture(writer.plan, writer, guard(30), ORIGIN)
    c = MapNativeProcessCollector(requests, notes=notes)
    page = NotesPage()
    if fault in ("attach", "detach"):
        page.listener_fault = fault
    try:
        if fault == "attach":
            with pytest.raises(OSError):
                c.attach(page, spec, guard())
        else:
            c.attach(page, spec, guard())
            response = NotesResponse()
            if fault == "body":
                response.error = OSError("original Notes capture failed")
            page.listener(response)
            original = readout(spec, 0)
            if fault == "body":
                with pytest.raises(OSError):
                    c.observe(page, original, guard())
                assert requests.last_readout is c.surface.last_readout is original
                with pytest.raises(EvidenceIntegrityError):
                    c.before_action(guard())
            else:
                c.observe(page, original, guard())
                c.finish(guard())
                assert response.reads == 1 and notes.last_readout is original
    finally:
        if fault == "detach":
            with pytest.raises(BaseExceptionGroup):
                c.close(guard())
        else:
            c.close(guard())
    assert (
        requests.relay.physical_closed
        and requests.state == "closed"
        and page.listener is None
    )
    handle = writer.seal(guard())
    closed = json.loads(
        MapArtifactReader(writer.plan, tmp_path, authority).read(
            handle, "map-notes-close.json", guard()
        )
    )
    assert closed["complete"] is (fault == "normal")


def test_cancel_after_known_notes_bytes_keeps_body_and_stops_next_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, page, original, writer, authority = notes_case(tmp_path)
    first, second = NotesResponse(), NotesResponse()

    class Cancel:
        cancelled = False

        def checkpoint(self) -> float:
            if self.cancelled:
                raise OperationStopped("CANCELLED", "original-notes-read")
            return 10.0

        def wait(self, seconds: float) -> None:
            raise AssertionError("No additional browser wait")

    control = Cancel()

    def body() -> bytes:
        first.reads += 1
        control.cancelled = True
        assert isinstance(first.raw, bytes)
        return first.raw

    monkeypatch.setattr(first, "body", body)
    page.listener(first)
    page.listener(second)
    with pytest.raises(OperationStopped) as error:
        c.observe(page, original, control)
    assert (
        error.value.reason_code == "CANCELLED"
        and first.reads == 1
        and second.reads == 0
    )
    c.close(guard())
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert reader.read(handle, "map-notes-0.bin", guard()) == first.raw
    closed = json.loads(reader.read(handle, "map-notes-close.json", guard()))
    assert (
        not closed["complete"]
        and closed["pending_unattempted"] == 1
        and second.reads == 0
    )


def test_body_and_end_record_failures_both_preserved(tmp_path: Path) -> None:
    c, page, original, writer, _ = notes_case(tmp_path)
    c.sink = FailedSink(writer, "map-notes-0-end.json")
    response = NotesResponse()
    response.error = OSError("original Notes network read unknown")
    page.listener(response)
    with pytest.raises(BaseExceptionGroup) as error:
        c.observe(page, original, guard())
    assert len(error.value.exceptions) == 2
    assert error.value.exceptions[0] is response.error
    assert isinstance(error.value.exceptions[1], OSError)
    c.close(guard())
    assert response.reads == 1 and len(c.errors) >= 2


def test_close_record_unknown_is_not_retried(tmp_path: Path) -> None:
    c, page, _, writer, _ = notes_case(tmp_path)
    sink = FailedSink(writer, "map-notes-close.json")
    c.sink = sink
    for _ in range(2):
        with pytest.raises(BaseExceptionGroup):
            c.close(guard())
    assert sink.calls == 1 and page.listener is None


def test_pending_body_close_failure_remains_unknown_on_repeat(tmp_path: Path) -> None:
    c, page, _, writer, authority = notes_case(tmp_path)
    response = NotesResponse()
    response.error = OSError("close-time original Notes body unknown")
    page.listener(response)
    for _ in range(2):
        with pytest.raises(BaseExceptionGroup):
            c.close(guard())
    assert response.reads == 1 and page.listener is None
    handle = writer.seal(guard())
    closed = json.loads(
        MapArtifactReader(writer.plan, tmp_path, authority).read(
            handle, "map-notes-close.json", guard()
        )
    )
    assert (
        not closed["complete"]
        and "close-time original Notes body unknown" in closed["errors"][0]
    )
