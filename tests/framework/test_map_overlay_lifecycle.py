"""Existing task requests composed with full private state and original reset."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.map_state import MapPersistentState
from lab_generate_skill.sites.map.state_guard import MapStateChanged
from lab_generate_skill.sites.map.state_rules import fingerprint
from lab_generate_skill.sites.map.tasks.overlay_recovery import (
    OverlaySnapshot,
    OverlayObserved,
    OverlayRestored,
    OverlayResumed,
)
from map_overlay_lifecycle_fixtures import OverlayCase
from map_service_generations_fixtures import GenerationCase
from test_map_service_generations import generations
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


@pytest.fixture
def overlay(generations: GenerationCase) -> OverlayCase:
    return OverlayCase(generations)


@pytest.mark.parametrize("forced", [False, True])
def test_same_instance_snapshot_prepare_capture_restore_resume_full_private_read(
    overlay: OverlayCase, forced: bool
) -> None:
    c = overlay
    prepared = c.prepare()
    observed = OverlayObserved.model_validate_json(prepared.private_result)
    assert c.lifecycle.snapshot is not None
    original = c.lifecycle.snapshot.native.state_sha256
    req = SiteCaptureRequest(
        inspection=c.request("inspect"),
        collector_id="map-overlay-state",
        collector_version="1",
    )
    captured = c.lifecycle.capture_task(req, control=guard())
    assert captured.request_sha256 == req.digest
    captured_state = OverlayObserved.model_validate_json(captured.private_result)
    assert captured_state.native.state_sha256 == original
    if forced:
        c.generations.force()
    restored = c.lifecycle.execute_task(c.request("restore"), control=guard())
    restore = OverlayRestored.model_validate_json(restored.private_result)
    assert restore.cleared.stopped.forced_namespace is forced
    assert c.lifecycle.phase == "restored" and c.reset.state == "retired"
    request = c.resume_request(restored)
    returned = c.resume.resume_frontend(request, control=guard())
    resumed = OverlayResumed.model_validate_json(returned.private_result)
    assert resumed.resumed.before_sha256 == resumed.resumed.after_sha256 == original
    assert c.lifecycle.phase == "resumed" and c.reset.state == "resumed"
    assert c.reset.spec.endpoint == resumed.resumed.endpoint
    for native in (
        c.lifecycle.snapshot.native,
        observed.native,
        captured_state.native,
        resumed.native,
    ):
        data = c.read(native)
        raw = json.loads(data)
        assert hashlib.sha256(data).hexdigest() == native.file.sha256
        assert (
            fingerprint(
                MapPersistentState.model_validate_json(json.dumps(raw["persistent"])),
                raw["database"].encode(),
            )
            == raw["sha256"]
            == original
        )
        assert raw["request_sha256"] == native.request_sha256
    assert len(c.publisher.results) == 4
    assert (
        c.root / "tmp/cache/assets/sprockets/compiled.js"
    ).read_bytes() == b"same deployment compiled bytes"
    assert not (c.root / "tmp/cache/session").exists()
    with pytest.raises(OwnershipConflict):
        c.resume.resume_frontend(request, control=guard())
    assert c.generations.owned is not None and len(c.generations.owned.records) == 11
    facts = c.generations.instance.stop(guard())
    assert len(facts) == 11 and all(f.state == "reaped" for f in facts)
    assert c.generations.case.ports.lease.releases == 0


def test_snapshot_only_restore_original_parent_and_resume(overlay: OverlayCase) -> None:
    c = overlay
    c.snapshot()
    restored = c.lifecycle.execute_task(c.request("restore"), control=guard())
    c.resume.resume_frontend(c.resume_request(restored), control=guard())
    assert c.lifecycle.phase == "resumed" and len(c.publisher.results) == 2


@pytest.mark.parametrize(
    "change",
    ["snapshot", "binding", "input", "attempt", "allocation", "recovery", "parent"],
)
def test_forged_restore_rejected_before_retirement(
    overlay: OverlayCase, change: str
) -> None:
    c = overlay
    c.prepare()
    request = c.request("restore")
    if change == "snapshot":
        request = request.model_copy(
            update={"snapshot_ref": c.put(b"wrong", "map-overlay-snapshot/1")}
        )
    elif change == "binding":
        request = request.model_copy(
            update={"binding_ref": c.put(b"other", "task-binding/1")}
        )
    elif change == "input":
        request = request.model_copy(update={"private_input": "{}"})
    else:
        field = {
            "attempt": "attempt_id",
            "allocation": "allocation_id",
            "recovery": "recovery_ref",
            "parent": "parent_operation_id",
        }[change]
        value: Any = (
            c.put(b"other", "recovery-plan/1") if change == "recovery" else "other"
        )
        request = request.model_copy(
            update={"operation": request.operation.model_copy(update={field: value})}
        )
    with pytest.raises((ValueError, OwnershipConflict)):
        c.lifecycle.execute_task(request, control=guard())
    assert c.lifecycle.phase == "prepared" and c.reset.state == "new"
    assert c.generations.rails().quiet_calls == 0


@pytest.mark.parametrize("action", ["prepare", "inspect", "restore"])
def test_dirty_state_quarantines_without_clearing_guard(
    overlay: OverlayCase, action: str
) -> None:
    c = overlay
    c.snapshot()
    if action != "prepare":
        c.lifecycle.execute_task(c.request("prepare"), control=guard())
    c.sql.value["changed"] = ["public.notes"]
    with pytest.raises(MapStateChanged) as caught:
        c.lifecycle.execute_task(c.request(action), control=guard())
    assert c.lifecycle.phase == "quarantined" and c.lifecycle.error is caught.value
    assert c.reset.guard.state == "changed" and c.sql.value["changed"] == [
        "public.notes"
    ]
    assert c.generations.rails().quiet_calls == 0
    with pytest.raises(InvalidTransition):
        c.lifecycle.execute_task(c.request(action, "another"), control=guard())


def test_readonly_inspection_can_have_new_id_but_duplicate_cannot_repeat(
    overlay: OverlayCase,
) -> None:
    c = overlay
    c.prepare()
    first = c.request("inspect", "inspect1")
    c.lifecycle.execute_task(first, control=guard())
    size = len(c.sql.calls)
    with pytest.raises(InvalidTransition):
        c.lifecycle.execute_task(first, control=guard())
    assert len(c.sql.calls) == size
    c.lifecycle.execute_task(c.request("inspect", "inspect2"), control=guard())
    assert len(c.publisher.results) == 4


def test_permission_failure_preserves_observation_and_blocks_task_replay(
    overlay: OverlayCase,
) -> None:
    c = overlay
    c.authority.denied = True
    with pytest.raises(PermissionError) as caught:
        c.snapshot()
    assert (
        c.lifecycle.phase == "quarantined" and c.lifecycle.last_observation is not None
    )
    assert (
        getattr(caught.value, "map_native_observation") is c.lifecycle.last_observation
    )
    assert len(c.publisher.writers) == 1 and not c.publisher.writers[0].root.exists()
    with pytest.raises(InvalidTransition):
        c.lifecycle.execute_task(c.request("snapshot", "again"), control=guard())


def test_wrong_owner_and_unsupported_capture_have_no_effect(
    overlay: OverlayCase,
) -> None:
    c = overlay
    with ThreadPoolExecutor() as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(c.snapshot).result()
    assert not c.sql.calls[2:] and not c.publisher.attempts
    c.prepare()
    req = SiteCaptureRequest(
        inspection=c.request("inspect"), collector_id="other", collector_version="1"
    )
    with pytest.raises(ValueError):
        c.lifecycle.capture_task(req, control=guard())
    assert c.lifecycle.phase == "prepared" and "inspect" not in c.lifecycle.operations


def test_cancelled_restore_preserves_original_namespace_and_no_second_attempt(
    overlay: OverlayCase,
) -> None:
    c = overlay
    c.prepare()
    error = OperationStopped("CANCELLED", "original-restore")
    c.generations.rails().retire_error = error
    with pytest.raises(OperationStopped) as caught:
        c.lifecycle.execute_task(c.request("restore"), control=guard())
    assert (
        caught.value is error is c.lifecycle.error
        and c.lifecycle.phase == "quarantined"
    )
    assert c.reset.state == "failed" and c.reset.error is error
    assert c.generations.rails().quiet_calls == 1
    with pytest.raises(InvalidTransition):
        c.lifecycle.execute_task(c.request("restore", "again"), control=guard())
    assert len(c.generations.groups) == 10


def test_forged_resume_receipt_no_new_service(overlay: OverlayCase) -> None:
    c = overlay
    c.prepare()
    restored = c.lifecycle.execute_task(c.request("restore"), control=guard())
    req = c.resume_request(restored).model_copy(
        update={"restore_result_ref": c.put(b"wrong", "site-task-result/1")}
    )
    with pytest.raises(OwnershipConflict):
        c.resume.resume_frontend(req, control=guard())
    assert (
        not c.resume.attempted
        and c.lifecycle.phase == "restored"
        and len(c.generations.groups) == 10
    )


@pytest.mark.parametrize(
    "value",
    ["", "{}", "[]", "null", "{", " ", "x" * 1048577],
    ids=["empty", "object", "array", "null", "truncated", "space", "over-limit"],
)
def test_bad_private_input_no_native_query_or_publication(
    overlay: OverlayCase, value: str
) -> None:
    c = overlay
    request = c.request("snapshot").model_copy(update={"private_input": value})
    before = len(c.sql.calls)
    with pytest.raises(ValueError):
        c.lifecycle.execute_task(request, control=guard())
    assert (
        len(c.sql.calls) == before
        and not c.publisher.attempts
        and c.lifecycle.phase == "new"
    )


@pytest.mark.parametrize("phase", ["prepare", "restore"])
def test_independent_result_validation_rejects_wrong_snapshot_bytes(
    overlay: OverlayCase, phase: str
) -> None:
    c = overlay
    prepared = c.prepare()
    result = (
        prepared
        if phase == "prepare"
        else c.lifecycle.execute_task(c.request("restore"), control=guard())
    )
    raw = json.loads(result.private_result)
    raw["request"]["snapshot_ref"] = c.put(
        b"other-snapshot", "map-overlay-snapshot/1"
    ).model_dump(mode="json")
    model = OverlayObserved if phase == "prepare" else OverlayRestored
    with pytest.raises(OwnershipConflict, match="snapshot bytes"):
        model.model_validate_json(json.dumps(raw))


def test_resume_health_failure_keeps_new_generation_and_never_relaunches(
    overlay: OverlayCase,
) -> None:
    c = overlay
    c.prepare()
    restored = c.lifecycle.execute_task(c.request("restore"), control=guard())
    request = c.resume_request(restored)
    c.generations.case.commands.http = [b'{"status":503,"body_base64":"ZmFpbGVk"}']
    with pytest.raises(ValueError):
        c.resume.resume_frontend(request, control=guard())
    assert c.lifecycle.phase == "quarantined" and c.reset.state == "failed"
    assert (
        c.resume.attempted
        and c.resume.result is None
        and len(c.generations.groups) == 11
    )
    assert (
        c.generations.owned is not None
        and c.generations.owned.active["rails_server"].pin is None
    )
    with pytest.raises(OwnershipConflict):
        c.resume.resume_frontend(request, control=guard())
    assert len(c.generations.groups) == 11
    assert len(c.generations.instance.stop(guard())) == 11
