"""Original failed start: confirm domains closed while preserving primary failure."""

import base64
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.lifecycle import ResourceRecord
from source_review_records import ReadOnlyEvidence, raw_json
from test_slurm_commands import guard

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/check-4851075"
)


@pytest.mark.parametrize(
    "job_id,error_type,last_function",
    [(4851075, "ValueError", "private_style"), (4851283, "CommandFailure", "run")],
)
def test_original_failed_start_closed_resources_without_browser_or_actor_replay(
    job_id: int, error_type: str, last_function: str
) -> None:
    root = ROOT.parent / f"check-{job_id}"
    store = ReadOnlyEvidence(root / "map-actor-native/resource/evidence")
    control = guard(60)
    actor = json.loads((root / "map-actor-native/facts.json").read_bytes())
    site = json.loads(Path(actor["site_facts_path"]).read_bytes())
    assert actor["paid_calls"] == 0 and actor["actor"] == {}
    assert (
        not site["passed"] and "started" not in site and "prepared_browser" not in site
    )
    journal = next((root / "map-actor-native/resource/journal").glob("*.resource.json"))
    rows: list[tuple[str, Any]] = [
        ("site", site["resource_record"]),
        ("actor", json.loads(journal.read_bytes())),
    ]
    for role, value in rows:
        record = ResourceRecord.model_validate_json(json.dumps(value))
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        acquisition = raw_json(store, record.events[1].evidence[0], control)
        acquired = raw_json(store, record.events[2].evidence[0], control)
        ended = raw_json(store, record.events[-1].evidence[0], control)
        assert (
            acquired["token"]
            == ended["token"]
            == acquisition["token"]
            == record.token.model_dump(mode="json")
        )
        assert (
            acquired["spec_sha256"]
            == ended["spec_sha256"]
            == acquisition["configuration_ref"]["sha256"]
        )
        ending = ended["details"] if role == "site" else ended
        started = acquired["details"]["ready"] if role == "site" else acquired["step"]
        target = started["controller"]["target"]
        closed = ending["step_closed"]
        assert (
            closed["target"] == target
            and closed["quiescence"]["original"] == target["worker"]
        )
        assert closed["quiescence"]["writer_status"] in ("missing", "reused")
        assert ending["primary"]["type_name"] == "SiteWorkerFailure"
        assert (
            ending["cleanup_errors"] == []
            and ending["termination"]["state"] == "reaped"
            and ending["termination"]["cleanup_errors"] == []
        )
        raw = raw_json(store, closed["evidence"], control)
        assert (
            raw["phase"] == "closed"
            and raw["target"] == target
            and raw["kernel"]
            and raw["commands"]
            and raw["error"] is None
        )
        assert all(c["complete"] and c["returncode"] == 0 for c in raw["commands"])
        if role == "site":
            reply = ending["last_reply"]
            assert (
                reply["phase"] == "start"
                and reply["sequence"] == 2
                and reply["started"] is None
                and reply["task_result"] is None
            )
            assert reply["error"]["type_name"] == error_type
            assert reply["error"]["frames"][-1]["function"] == last_function
            assert all(e["state"] == "reaped" for e in reply["exits"])
            if job_id == 4851283:
                assert reply["error"]["reason_code"] == "NATIVE_COMMAND_FAILED"
                assert {e["service"] for e in reply["exits"]} == {
                    "search_postgres",
                    "search_http",
                    "route_car",
                    "route_bike",
                    "route_foot",
                    "tile_postgres",
                    "renderd",
                    "tile_http",
                }
                capture = raw_json(store, ending["worker_capture_ref"], control)
                stderr = base64.b64decode(
                    capture["commands"][0]["stderr_base64"]
                ).decode()
                failures = [
                    json.loads(line.removeprefix("SITE_NATIVE_FAILURE "))
                    for line in stderr.splitlines()
                    if line.startswith("SITE_NATIVE_FAILURE ")
                ]
                assert len(failures) == 1
                failure = failures[0]
                assert failure["complete"] and failure["returncode"] == 1
                assert not failure["stderr_truncated"]
                assert b"Net::ReadTimeout" in base64.b64decode(failure["stderr_base64"])
