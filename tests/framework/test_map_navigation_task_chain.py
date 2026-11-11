"""All8 current task identities through shared physical state/reset/resume ports."""

import json
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.sites.map.tasks.navigation_recovery import (
    NavigationSnapshot,
    NavigationObserved,
    NavigationRestored,
    NavigationResumed,
)
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlaySnapshot
from lab_generate_skill.sites.map.tasks.reference_dispatch import MapReferenceDispatch
from map_navigation_task_fixtures import NavigationTaskCase
from map_navigation_group_cases import SOURCES
from map_service_generations_fixtures import GenerationCase
from test_map_service_generations import generations as generations
from test_map_instance import case as case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_each_group_member_snapshot_prepare_capture_restore_resume_and_full_files(
    generations: GenerationCase, source: str
) -> None:
    c = NavigationTaskCase(generations, source)
    snapshot = NavigationSnapshot.model_validate_json(c.snapshot().private_result)
    prepared = c.lifecycle.execute_task(c.request("prepare"), control=guard())
    observed = NavigationObserved.model_validate_json(prepared.private_result)
    cap = SiteCaptureRequest(
        inspection=c.request("inspect"),
        collector_id="map-navigation-state",
        collector_version="1",
    )
    captured = NavigationObserved.model_validate_json(
        c.lifecycle.capture_task(cap, control=guard()).private_result
    )
    restored = c.lifecycle.execute_task(c.request("restore"), control=guard())
    reset = NavigationRestored.model_validate_json(restored.private_result)
    resume = c.resume_request(restored)
    proof = NavigationResumed.model_validate_json(
        c.resume.resume_frontend(resume, control=guard()).private_result
    )
    assert snapshot.request.task.source_task_id == source
    assert (
        proof.restored == reset
        and proof.native.state_sha256 == snapshot.native.state_sha256
    )
    assert c.lifecycle.phase == "resumed" and c.resume.attempted
    for native in [snapshot.native, observed.native, captured.native, proof.native]:
        raw = MapArtifactReader(native.plan, c.workspace, c.authority).read(
            native.handle, "state.json", guard()
        )
        value = json.loads(raw)
        assert value["request_sha256"] == native.request_sha256
        assert value["sha256"] == snapshot.native.state_sha256
        assert native.plan.scope.task == c.spec.task
    with pytest.raises(ValueError):
        OverlaySnapshot.model_validate_json(snapshot.model_dump_json())
    with pytest.raises(OwnershipConflict):
        c.resume.resume_frontend(resume, control=guard())
    assert len(c.publisher.results) == 4


@pytest.mark.parametrize("change", ["tag", "binding", "input", "task", "parent"])
def test_navigation_forged_restore_refuses_before_retirement(
    generations: GenerationCase, change: str
) -> None:
    c = NavigationTaskCase(generations, SOURCES[0])
    c.prepare()
    request = c.request("restore")
    if change == "tag":
        assert c.lifecycle.snapshot is not None
        request = request.model_copy(
            update={
                "snapshot_ref": c.physical.put(
                    c.lifecycle.snapshot.model_dump_json().encode(),
                    "map-overlay-snapshot/1",
                )
            }
        )
    elif change == "binding":
        request = request.model_copy(
            update={"binding_ref": c.physical.put(b"another", "task-binding/1")}
        )
    elif change == "input":
        request = request.model_copy(update={"private_input": "{}"})
    elif change == "task":
        request = request.model_copy(
            update={"task": request.task.model_copy(update={"task_id": "other"})}
        )
    else:
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"parent_operation_id": "other"}
                )
            }
        )
    before = len(c.sql.calls)
    with pytest.raises((ValueError, OwnershipConflict)):
        c.lifecycle.execute_task(request, control=guard())
    assert (
        c.reset.state == "new"
        and c.lifecycle.phase == "prepared"
        and len(c.sql.calls) == before
    )


@pytest.mark.parametrize(
    "collector", ["map-overlay-state", "map-native-reference", "unknown"]
)
def test_navigation_does_not_use_MapData_or_unknown_capture(
    generations: GenerationCase, collector: str
) -> None:
    c = NavigationTaskCase(generations, SOURCES[0])
    c.prepare()
    before = len(c.sql.calls)
    with pytest.raises(ValueError):
        c.lifecycle.capture_task(
            SiteCaptureRequest(
                inspection=c.request("inspect"),
                collector_id=collector,
                collector_version="1",
            ),
            control=guard(),
        )
    unused: Any = object()
    with pytest.raises(ValueError, match="cannot dispatch navigation"):
        MapReferenceDispatch(c.lifecycle, unused, unused)
    assert len(c.sql.calls) == before and c.lifecycle.phase == "prepared"


@pytest.mark.parametrize("value", [None, {}, [], "", False, 1])
def test_navigation_bad_request_has_no_state_query_or_file(
    generations: GenerationCase, value: Any
) -> None:
    c = NavigationTaskCase(generations, SOURCES[0])
    before = len(c.sql.calls)
    with pytest.raises(ValueError):
        c.lifecycle.execute_task(cast(SiteTaskRequest, value), control=guard())
    assert (
        not c.publisher.writers
        and not c.lifecycle.operations
        and len(c.sql.calls) == before
    )


def test_navigation_lost_publication_ack_preserves_file_and_quarantines_no_retry(
    generations: GenerationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = NavigationTaskCase(generations, SOURCES[0])
    publish = c.publisher.publish
    first = TimeoutError("synthetic lost acknowledgment after native file sealed")

    def lose_ack(*args: Any, **kwargs: Any) -> Any:
        publish(*args, **kwargs)
        raise first

    monkeypatch.setattr(c.publisher, "publish", lose_ack)
    with pytest.raises(TimeoutError) as caught:
        c.lifecycle.execute_task(c.request("snapshot"), control=guard())
    assert caught.value is first and c.lifecycle.phase == "quarantined"
    assert c.publisher.writers[0].state == "sealed" and len(c.publisher.results) == 1
    before = len(c.sql.calls)
    with pytest.raises(InvalidTransition):
        c.lifecycle.execute_task(c.request("snapshot"), control=guard())
    assert len(c.sql.calls) == before and len(c.publisher.results) == 1


def test_navigation_cancellation_before_effect_keeps_original_new_state(
    generations: GenerationCase,
) -> None:
    c = NavigationTaskCase(generations, SOURCES[0])
    before = len(c.sql.calls)

    class Cancelled:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "snapshot")

        def wait(self, seconds: float) -> None:
            raise OperationStopped("CANCELLED", "snapshot")

    with pytest.raises(OperationStopped):
        c.lifecycle.execute_task(c.request("snapshot"), control=Cancelled())
    assert c.lifecycle.phase == "new" and not c.lifecycle.operations
    assert not c.publisher.writers and len(c.sql.calls) == before


@pytest.mark.parametrize("phase", ["restore", "resume"])
def test_navigation_partial_physical_recovery_keeps_failure_and_blocks_replay(
    generations: GenerationCase, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    c = NavigationTaskCase(generations, SOURCES[0])
    c.prepare()
    first = TimeoutError("synthetic lost physical recovery acknowledgment")
    if phase == "restore":
        original = c.reset.begin

        def lost_restore(*args: Any, **kwargs: Any) -> Any:
            original(*args, **kwargs)
            raise first

        monkeypatch.setattr(c.reset, "begin", lost_restore)
        request = c.request("restore")
        with pytest.raises(TimeoutError) as caught:
            c.lifecycle.execute_task(request, control=guard())
        before = len(c.sql.calls)
        with pytest.raises(InvalidTransition):
            c.lifecycle.execute_task(request, control=guard())
    else:
        restored = c.lifecycle.execute_task(c.request("restore"), control=guard())
        request_resume = c.resume_request(restored)
        original_resume = c.reset.resume

        def lost_resume(*args: Any, **kwargs: Any) -> Any:
            original_resume(*args, **kwargs)
            raise first

        monkeypatch.setattr(c.reset, "resume", lost_resume)
        with pytest.raises(TimeoutError) as caught:
            c.resume.resume_frontend(request_resume, control=guard())
        before = len(c.sql.calls)
        with pytest.raises(OwnershipConflict):
            c.resume.resume_frontend(request_resume, control=guard())
    assert caught.value is first and c.lifecycle.error is first
    assert c.lifecycle.phase == "quarantined" and len(c.sql.calls) == before
