"""Fixed Map dispatch -> original acquired journal -> real state files and task RPC."""

from collections.abc import Iterator
import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.adapters.map_artifacts.site_storage import (
    OriginalMapStateStorage,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_resume import SiteResumeIntent
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    EvidenceIntegrityError,
)
from lab_generate_skill.sites.map.tasks.overlay_recovery import (
    OverlayObserved,
    OverlayResumed,
)
from map_registered_worker_fixtures import RegisteredMapCase
from site_instance_fixtures import node_path
from test_site_resource import enter, inspect
from test_site_capture import Authority as CaptureAuthority
from site_resume_fixtures import Authority as ResumeAuthority, put
from test_slurm_commands import guard


@pytest.fixture
def registered_map(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[RegisteredMapCase]:
    value = RegisteredMapCase(node_path, monkeypatch)
    try:
        yield value
    finally:
        value.close_sockets()


def test_original_dispatch_resource_state_task_capture_resume_and_closed_read(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    with enter(c.resource) as registered:
        assert c.worker is not None and c.worker.tasks is not None
        assert c.worker.configuration.schema_version == "site-worker-configuration/6"
        assert (
            inspect(c.resource).state == "acquired" and len(c.generation.groups) == 10
        )
        assert c.worker.tasks.guard.state == "ready"
        snapshot = registered.tasks.execute_task(c.request("snapshot"), control=guard())
        c.snapshot_ref = c.put(
            snapshot.private_result.encode(), "map-overlay-snapshot/1"
        )
        registered.tasks.execute_task(c.request("prepare"), control=guard())
        cap = SiteCaptureRequest(
            inspection=c.request("inspect"),
            collector_id="map-overlay-state",
            collector_version="1",
        )
        intent = put(
            c.resource.evidence,
            SiteCaptureIntent(
                configuration_sha256=hashlib.sha256(
                    c.configuration.model_dump_json().encode()
                ).hexdigest(),
                request=cap,
            ),
        )
        capture = registered.capture.capture_task(
            cap, intent, CaptureAuthority(c.resource.evidence), control=guard()
        )
        state = OverlayObserved.model_validate_json(capture.private_result)
        restored = registered.tasks.execute_task(c.request("restore"), control=guard())
        resume = c.resume_request(restored)
        resume_intent = put(
            c.resource.evidence,
            SiteResumeIntent(
                configuration_sha256=hashlib.sha256(
                    c.configuration.model_dump_json().encode()
                ).hexdigest(),
                request=resume,
            ),
        )
        result = registered.resume.resume_frontend(
            resume, resume_intent, ResumeAuthority(c.resource.evidence), control=guard()
        )
        proof = OverlayResumed.model_validate_json(result.private_result)
        assert proof.resumed.endpoint == registered.site.instance.endpoint
        assert proof.native.state_sha256 == state.native.state_sha256
        assert len(c.generation.groups) == 11 and c.worker.tasks.phase == "resumed"
        started = registered.site.instance
    assert inspect(c.resource).state == "closed" and c.worker.closed
    assert isinstance(c.worker.storage, OriginalMapStateStorage)
    assert c.worker.storage.state == "stopped"
    assert len(c.worker.storage.publisher.results) == 4
    # Independent original controller can read after closure, never write.
    c.observer = "controller"
    access = OriginalMapSiteAccess(
        c.configuration, "controller", c.reader, None, started
    )
    plan = access.plan(cap.inspection, guard())
    assert plan == state.native.plan
    data = MapArtifactReader(plan, c.workspace, access).read(
        state.native.handle, "state.json", guard()
    )
    assert json.loads(data)["sha256"] == state.native.state_sha256
    with pytest.raises(OwnershipConflict):
        access.verify(plan, "initialize", guard())
    assert c.generation.owned is not None
    assert all(r.stop_facts is not None for r in c.generation.owned.records)


def test_worker_missing_original_acquisition_does_not_create_roots(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    from lab_generate_skill.bootstrap.site_instance import build_site_instance

    worker = build_site_instance(c.configuration, worker_guard=c.live)
    with pytest.raises(EvidenceIntegrityError, match="Unsafe snapshot lock") as caught:
        worker.start(guard())
    assert isinstance(caught.value.__cause__, FileNotFoundError)
    assert c.configuration.map_inputs is not None
    assert not Path(c.configuration.map_inputs.artifact_root).exists()
    assert not Path(c.configuration.files.node_root).exists()


def test_foreign_scope_rejected_in_original_worker_before_native_query(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    with enter(c.resource):
        assert c.worker is not None
        before = len(c.sql.calls)
        req = c.request("snapshot")
        changed = req.model_copy(
            update={
                "operation": req.operation.model_copy(update={"attempt_id": "other"})
            }
        )
        with pytest.raises(OwnershipConflict):
            c.worker.execute_task(changed, control=guard())
        changed = req.model_copy(update={"private_input": req.private_input + " "})
        with pytest.raises(OwnershipConflict):
            c.worker.execute_task(changed, control=guard())
        assert len(c.sql.calls) == before
        assert isinstance(c.worker.storage, OriginalMapStateStorage)
        assert not c.worker.storage.publisher.writers


def test_map_binding_is_once_and_old_worker_loses_permission_after_close(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    with enter(c.resource) as registered:
        assert c.worker is not None and isinstance(
            c.worker.storage, OriginalMapStateStorage
        )
        storage = c.worker.storage
        with pytest.raises(InvalidTransition):
            storage.initialize(guard())
        with pytest.raises(InvalidTransition):
            storage.bind_instance(registered.site.instance, guard())
        plan = storage.access.plan(c.request("snapshot"), guard())
    with pytest.raises(InvalidTransition):
        storage.access.verify(plan, "read", guard())
    fresh = OriginalMapSiteAccess(
        c.configuration, "worker", c.reader, c.live, registered.site.instance
    )
    with pytest.raises(OwnershipConflict):
        fresh.plan(c.request("snapshot"), guard())
