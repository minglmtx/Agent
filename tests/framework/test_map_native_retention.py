"""Real native HTTP/batch + complete file publication + independent DB comparison."""

import hashlib
import json
from pathlib import Path
import time
from typing import Any
import pytest
from lab_generate_skill.sites.map.native_retention import NativeBatchRetention
from lab_generate_skill.sites.map.native_http import (
    NativeMapHttpClient,
    NativeHttpReadError,
)
from lab_generate_skill.sites.map.native_batch import complete_cap_response
from lab_generate_skill.sites.map.native_batch_records import BatchRecords
from lab_generate_skill.sites.map.native_compare import compare_database
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from map_artifact_fixtures import case
from map_http_fixtures import http_fixture
from map_xml_fixtures import ROOT
from test_map_native_database import database
from test_slurm_commands import guard


def test_actual_native_http_batch_complete_files_independent_readback(
    tmp_path: Path,
) -> None:
    w, a = case(tmp_path)
    w.initialize(guard())
    retain = NativeBatchRetention("request-0", w, guard(60))
    with http_fixture("batch") as server:
        deadline = time.monotonic() + 10
        original = NativeMapHttpClient(server.origin).fetch(ROOT, deadline)
        payload, summary = complete_cap_response(
            ROOT,
            original,
            (NativeMapHttpClient(server.origin), NativeMapHttpClient(server.origin)),
            deadline=deadline,
            preserve=retain,
        )
        assert len(server.calls) == 3 and summary["native_children"] == 2
    db = database()
    w.retain("adapted.osm", payload, guard())
    w.retain("independent-db.json", json.dumps(db).encode(), guard())
    handle = w.seal(guard())
    reader = MapArtifactReader(w.plan, tmp_path, a)
    manifest = reader.manifest(handle, guard())
    events = [
        json.loads(reader.read(handle, f.path, guard()))
        for f in manifest.artifact.files
        if f.path.startswith("request-") and f.path.endswith(".json")
    ]
    assert [e["event_index"] for e in events] == list(range(len(events)))
    for index in (0, 1, 2):
        rows = [e for e in events if e["request_index"] == index]
        assert (
            rows[0]["source_record"]["status"] == "started" and rows[0]["body"] is None
        )
        completed = next(e for e in rows if e["body"] is not None)
        assert completed["source_record"]["http_status"] == (400 if index == 0 else 200)
        body = reader.read(handle, completed["body"]["path"], guard())
        assert hashlib.sha256(body).hexdigest() == completed["source_record"]["sha256"]
    actual = compare_database(
        reader.read(handle, "adapted.osm", guard()),
        ROOT,
        json.loads(reader.read(handle, "independent-db.json", guard())),
        response_kind="adapted_union",
    )
    assert actual["passed"] and not actual["provenance_verified"]


def test_actual_partial_http_retained_without_retry(tmp_path: Path) -> None:
    w, a = case(tmp_path)
    w.initialize(guard())
    retain = NativeBatchRetention("partial", w, guard())
    records = BatchRecords(retain)
    row = records.start((), ROOT)
    with http_fixture("partial") as server:
        began = time.monotonic()
        with pytest.raises(NativeHttpReadError) as caught:
            NativeMapHttpClient(server.origin).fetch(ROOT, began + 3)
        records.failed(row, caught.value, began)
        assert len(server.calls) == 1
    h = w.seal(guard())
    reader = MapArtifactReader(w.plan, tmp_path, a)
    assert retain.last_event is not None and retain.last_body is not None
    event = json.loads(reader.read(h, retain.last_event.path, guard()))
    assert (
        not event["source_record"]["body_complete"]
        and reader.read(h, retain.last_body.path, guard()) == b"prefix"
    )


@pytest.mark.parametrize(
    "fault", ["index", "wrong-type", "hash", "size", "complete", "non-json"]
)
def test_invalid_original_event_rejected_before_file_writes(
    tmp_path: Path, fault: str
) -> None:
    w, _ = case(tmp_path)
    w.initialize(guard())
    retain = NativeBatchRetention("one", w, guard())
    row: dict[str, Any] = dict(
        request_index=0,
        bytes=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
        body_complete=True,
    )
    if fault == "index":
        row["request_index"] = 1
    elif fault == "wrong-type":
        row["request_index"] = False
    elif fault == "hash":
        row["sha256"] = "a" * 64
    elif fault == "size":
        row["bytes"] = True
    elif fault == "complete":
        row["body_complete"] = "yes"
    else:
        row["other"] = object()
    with pytest.raises((ValueError, TypeError, EvidenceIntegrityError)):
        retain(0, row, b"x")
    assert not w.files and not list(w.working.iterdir())


def test_body_survives_event_failure_and_no_transition_replay(tmp_path: Path) -> None:
    w, _ = case(tmp_path)
    w.initialize(guard())

    class FailedEvent:
        def retain(
            self, name: str, data: bytes, control: OperationControl
        ) -> ReleaseFile:
            if name.endswith(".json"):
                raise OSError("event persistence failed")
            return w.retain(name, data, control)

    retain = NativeBatchRetention("failure", FailedEvent(), guard())
    body = b"original"
    row = dict(
        request_index=0,
        bytes=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        body_complete=True,
    )
    with pytest.raises(OSError):
        retain(0, row, body)
    assert retain.last_body is not None and retain.pending_record is not None
    assert (w.working / retain.last_body.path).read_bytes() == body and retain.failed
    with pytest.raises(InvalidTransition):
        retain(0, row, body)
    assert len(w.files) == 1
