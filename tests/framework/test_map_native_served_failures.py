"""Evidence failure/cancellation and owner boundaries, without browser replay."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.sites.map.native_process_collector import (
    MapNativeProcessCollector,
)
from map_served_fixtures import served_case, Response, ORIGIN
from map_route_fixtures import collection
from test_slurm_commands import guard


class FailedSink:
    def __init__(self, writer: MapArtifactWriter, name: str) -> None:
        self.writer, self.name = writer, name
        self.calls = 0

    def retain(self, name: str, body: bytes, control: OperationControl) -> ReleaseFile:
        if name == self.name:
            self.calls += 1
            raise OSError("original served file write result unknown")
        return self.writer.retain(name, body, control)


@pytest.mark.parametrize("name", ["map-served-0.js", "map-actually-served.json"])
def test_original_response_write_failure_retains_known_bytes(
    tmp_path: Path, name: str
) -> None:
    c, page, responses, original, writer, _ = served_case(tmp_path)
    sink = FailedSink(writer, name)
    c.sink = sink
    for response in responses:
        page.listener(response)
    with pytest.raises(OSError):
        c.verify(page, original, guard())
    if name == "map-served-0.js":
        assert c.pending_body == responses[0].raw and responses[0].reads == 1
        assert all(response.reads == 0 for response in responses[1:])
    else:
        assert c.summary["passed"] and c.state == "failed"
    counts = [r.reads for r in responses]
    with pytest.raises(EvidenceIntegrityError):
        c.verify(page, original, guard())
    assert counts == [r.reads for r in responses] and sink.calls == 1
    c.close(guard())


def test_original_runtime_mismatch_and_summary_failure_both_preserved(
    tmp_path: Path,
) -> None:
    c, page, responses, original, writer, _ = served_case(tmp_path)
    c.sink = FailedSink(writer, "map-actually-served.json")
    page.runtime = None
    for response in responses:
        page.listener(response)
    with pytest.raises(BaseExceptionGroup) as error:
        c.verify(page, original, guard())
    assert len(error.value.exceptions) == 2
    assert isinstance(error.value.exceptions[0], EvidenceIntegrityError)
    assert isinstance(error.value.exceptions[1], OSError)
    assert c.state == "failed" and len(c.errors) == 2 and not c.summary["passed"]
    c.close(guard())


def test_original_served_close_unknown_not_retried(tmp_path: Path) -> None:
    c, page, _, _, writer, _ = served_case(tmp_path)
    sink = FailedSink(writer, "map-served-close.json")
    c.sink = sink
    for _ in range(2):
        with pytest.raises(BaseExceptionGroup):
            c.close(guard())
    assert sink.calls == 1 and page.listener is None


def test_cancel_during_original_body_read_retains_body_without_next_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, page, responses, original, writer, authority = served_case(tmp_path)

    class Cancel:
        cancelled = False

        def checkpoint(self) -> float:
            if self.cancelled:
                raise OperationStopped("CANCELLED", "original-script-read")
            return 10.0

        def wait(self, seconds: float) -> None:
            raise AssertionError("No new source wait")

    control = Cancel()
    original_body = responses[0].body

    def stopped_body() -> bytes:
        raw = original_body()
        assert isinstance(raw, bytes)
        control.cancelled = True
        return raw

    monkeypatch.setattr(responses[0], "body", stopped_body)
    for response in responses:
        page.listener(response)
    with pytest.raises(OperationStopped) as error:
        c.verify(page, original, control)
    assert error.value.reason_code == "CANCELLED" and responses[0].reads == 1
    assert all(response.reads == 0 for response in responses[1:])
    c.close(guard())
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    assert reader.read(handle, "map-served-0.js", guard()) == responses[0].raw
    summary = json.loads(reader.read(handle, "map-actually-served.json", guard()))
    assert not summary["passed"] and "CANCELLED" in summary["error"]


def test_candidate_budget_quarantines_without_body_reads(tmp_path: Path) -> None:
    c, page, _, original, _, _ = served_case(tmp_path)
    responses = [Response(page, "index.js", b"no read") for _ in range(257)]
    for response in responses:
        page.listener(response)
    assert len(c.responses) == 256 and c.errors
    with pytest.raises(EvidenceIntegrityError):
        c.verify(page, original, guard())
    assert all(response.reads == 0 for response in responses)
    c.close(guard())


def test_different_sink_cannot_join_original_process(tmp_path: Path) -> None:
    (tmp_path / "different").mkdir(mode=0o700)
    (tmp_path / "original").mkdir(mode=0o700)
    c, _, _, _, _, _ = served_case(tmp_path / "different")
    requests, _, _, _, _ = collection(tmp_path / "original", ORIGIN)
    try:
        with pytest.raises(OwnershipConflict):
            MapNativeProcessCollector(requests, served=c)
    finally:
        c.close(guard())
        requests.close(guard())
