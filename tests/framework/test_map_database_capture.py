"""Full selected native-file consumer combination; no actual Rails database here."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.state_guard import MapStateChanged
from map_database_capture_fixtures import CaptureCase, BOUNDS, payload
from map_instance_fixtures import InstanceCase
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


@pytest.fixture
def capture_case(case: InstanceCase) -> CaptureCase:
    return CaptureCase(case)


def test_full_instance_query_complete_file_guard_seal_independent_read(
    capture_case: CaptureCase,
) -> None:
    c = capture_case
    result = c.capture.capture(BOUNDS, "request0", guard(60))
    assert result.database.initial_node_ids == ("1",)
    assert c.tracker.initial is not None
    assert result.before_sha256 == result.after_sha256 == c.tracker.initial.sha256
    assert len(c.calls) == 1 and c.capture.state == "ready"
    assert len(c.capture.retained) == 4 and c.capture.results == [result]
    handle = c.writer.seal(guard())
    reader = MapArtifactReader(c.plan, Path(c.plan.workspace_root), c.authority)
    assert reader.read(handle, result.output.path, guard()) == c.body
    complete = json.loads(reader.read(handle, "request0-complete.json", guard()))
    assert complete["output"] == result.output.model_dump(mode="json")
    assert complete["artifact_plan_sha256"] == c.plan.digest
    with pytest.raises(InvalidTransition):
        c.capture.capture(BOUNDS, "request0", guard())
    assert len(c.calls) == 1


@pytest.mark.parametrize(
    "body", [b"", b"[]", b"{", b'{"x":1,"x":2}', b'{"x":NaN}', b"{}", b"null"]
)
def test_malformed_native_bytes_retained_before_parse_and_never_reissued(
    capture_case: CaptureCase, body: bytes
) -> None:
    c = capture_case
    c.body = body
    with pytest.raises(ValueError):
        c.capture.capture(BOUNDS, "request0", guard())
    assert (c.writer.working / "osm-expanded-request0.json").read_bytes() == body
    assert c.capture.state == "failed" and not c.capture.results
    assert not (c.writer.working / "request0-complete.json").exists()
    with pytest.raises(InvalidTransition):
        c.capture.capture(BOUNDS, "request1", guard())
    assert len(c.calls) == 1


def test_unknown_native_return_preserves_original_output_no_read_or_reissue(
    capture_case: CaptureCase,
) -> None:
    c = capture_case
    c.fail = OSError("original native command return unknown")
    with pytest.raises(OSError) as caught:
        c.capture.capture(BOUNDS, "request0", guard())
    assert caught.value is c.fail is c.capture.error
    export = c.capture.exports[0]
    assert (Path(export.host_directory) / export.output_name).read_bytes() == c.body
    assert len(c.capture.retained) == 2 and not c.capture.results
    with pytest.raises(InvalidTransition):
        c.capture.capture(BOUNDS, "request1", guard())
    assert len(c.calls) == 1


def test_persistent_change_after_query_keeps_raw_but_no_completion(
    capture_case: CaptureCase,
) -> None:
    c = capture_case
    c.dirty = True
    with pytest.raises(MapStateChanged):
        c.capture.capture(BOUNDS, "request0", guard())
    assert c.tracker.state == "changed" and c.capture.state == "failed"
    assert (c.writer.working / "osm-expanded-request0.json").read_bytes() == c.body
    assert not (c.writer.working / "request0-complete.json").exists()


def test_denied_evidence_prevents_native_dispatch(capture_case: CaptureCase) -> None:
    c = capture_case
    c.authority.denied = True
    with pytest.raises(PermissionError):
        c.capture.capture(BOUNDS, "request0", guard())
    assert c.calls == [] and c.capture.state == "failed"
    assert not Path(c.capture.exports[0].host_directory).exists()


@pytest.mark.parametrize(
    "bounds,label",
    [
        (None, "request0"),
        ([], "request0"),
        ([True, 0, 1, 1], "request0"),
        (BOUNDS, ""),
        (BOUNDS, "../escape"),
        (BOUNDS, 3),
    ],
)
def test_invalid_input_no_label_reservation_or_dispatch(
    capture_case: CaptureCase, bounds: object, label: Any
) -> None:
    c = capture_case
    with pytest.raises(ValueError):
        c.capture.capture(bounds, label, guard())
    assert c.calls == [] and c.capture.exports == [] and c.capture.labels == set()
    assert c.capture.state == "ready" and not c.writer.files


def test_wrong_owner_no_effect_and_wrong_resource_rejected(
    capture_case: CaptureCase,
) -> None:
    c = capture_case
    with ThreadPoolExecutor() as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(c.capture.capture, BOUNDS, "request0", guard()).result()
    changed = c.plan.model_copy(
        update={
            "token": c.plan.token.model_copy(update={"expected_resource_id": "other"})
        }
    )
    with pytest.raises(ValueError):
        c.build(artifacts=changed)
    assert not c.calls and not c.writer.files


def test_empty_native_selection_is_complete_negative_bytes_not_supported_result(
    capture_case: CaptureCase,
) -> None:
    c = capture_case
    raw = payload()
    raw.update(nodes=[], initial_node_ids=[])
    c.body = json.dumps(raw).encode()
    with pytest.raises(ValueError, match="nonempty"):
        c.capture.capture(BOUNDS, "request0", guard())
    assert (c.writer.working / "osm-expanded-request0.json").read_bytes() == c.body
    assert not c.capture.results


def test_cancellation_after_query_retains_output_and_blocks_reissue(
    capture_case: CaptureCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = capture_case
    stopped = OperationStopped("CANCELLED", "original-db-read")

    def read(plan: MapDatabaseExport, control: OperationControl) -> bytes:
        assert (Path(plan.host_directory) / plan.output_name).exists()
        raise stopped

    monkeypatch.setattr(c.files, "read", read)
    with pytest.raises(OperationStopped) as caught:
        c.capture.capture(BOUNDS, "request0", guard())
    assert caught.value is stopped is c.capture.error
    assert len(c.calls) == 1 and len(c.capture.retained) == 2
    with pytest.raises(InvalidTransition):
        c.capture.capture(BOUNDS, "request1", guard())


def test_sink_lost_ack_keeps_raw_and_blocks_new_query(
    capture_case: CaptureCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = capture_case
    original = c.writer.retain
    error = OSError("original retention ack unknown")

    def retain(name: str, data: bytes, control: OperationControl) -> Any:
        result = original(name, data, control)
        if name == "osm-expanded-request0.json":
            raise error
        return result

    monkeypatch.setattr(c.writer, "retain", retain)
    with pytest.raises(OSError) as caught:
        c.capture.capture(BOUNDS, "request0", guard())
    assert caught.value is error is c.capture.error
    assert (c.writer.working / "osm-expanded-request0.json").read_bytes() == c.body
    assert not c.capture.results
    with pytest.raises(InvalidTransition):
        c.capture.capture(BOUNDS, "request1", guard())
    assert len(c.calls) == 1
