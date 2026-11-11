"""All8 fixed registered RPC/intents/full files/closure, synthetic native effects."""

import hashlib
from pathlib import Path
import pytest
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_resume import SiteResumeIntent
from lab_generate_skill.sites.map.tasks.navigation_recovery import (
    NavigationObserved,
    NavigationResumed,
)
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path
from test_site_resource import enter, inspect
from test_site_capture import Authority as CaptureAuthority
from site_resume_fixtures import Authority as ResumeAuthority, put
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_registered_navigation_declared_fixture_preflight(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        assert c.configuration.map_inputs is not None
        assert c.configuration.map_inputs.scope == c.scope
        assert c.private.task == c.scope.task
        assert (
            c.configuration.map_inputs.private_input_sha256
            == hashlib.sha256(c.private.model_dump_json().encode()).hexdigest()
        )
        assert not c.sql.calls and c.worker is None
    finally:
        c.close_sockets()


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_fixed_RPC_capture_resume_resource_closed_readonly(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        with enter(c.resource) as registered:
            assert c.worker is not None and c.worker.tasks is not None
            assert c.worker.tasks.codecs.task == c.scope.task
            assert c.worker.references is None
            assert inspect(c.resource).state == "acquired"
            snapshot = registered.tasks.execute_task(
                c.request("snapshot"), control=guard()
            )
            c.snapshot_ref = c.put(
                snapshot.private_result.encode(), "map-navigation-snapshot/1"
            )
            registered.tasks.execute_task(c.request("prepare"), control=guard())
            cap = SiteCaptureRequest(
                inspection=c.request("inspect"),
                collector_id="map-navigation-state",
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
            captured = registered.capture.capture_task(
                cap, intent, CaptureAuthority(c.resource.evidence), control=guard()
            )
            state = NavigationObserved.model_validate_json(captured.private_result)
            before = len(c.sql.calls)
            with pytest.raises(ValueError):
                SiteCaptureRequest(
                    inspection=c.request("inspect", "missing-reference-selection"),
                    collector_id="map-native-reference",
                    collector_version="1",
                )
            selection = c.put(b"{}", "map-reference-selection/1")
            with pytest.raises(InvalidTransition):
                c.worker.capture_task(
                    SiteCaptureRequest(
                        inspection=c.request("inspect", "wrong-ref"),
                        collector_id="map-native-reference",
                        collector_version="1",
                        selection_ref=selection,
                    ),
                    control=guard(),
                )
            assert len(c.sql.calls) == before
            with pytest.raises(OwnershipConflict):
                c.worker.execute_task(
                    c.request("inspect", "wrong-source").model_copy(
                        update={
                            "task": c.scope.task.model_copy(update={"task_id": "other"})
                        }
                    ),
                    control=guard(),
                )
            assert len(c.sql.calls) == before
            restored = registered.tasks.execute_task(
                c.request("restore"), control=guard()
            )
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
                resume,
                resume_intent,
                ResumeAuthority(c.resource.evidence),
                control=guard(),
            )
            proof = NavigationResumed.model_validate_json(result.private_result)
            assert proof.native.state_sha256 == state.native.state_sha256
            assert c.worker.tasks.phase == "resumed"
            started = registered.site.instance
        assert inspect(c.resource).state == "closed" and c.worker.closed
        c.observer = "controller"
        closed_queries = len(c.sql.calls)
        access = OriginalMapSiteAccess(
            c.configuration, "controller", c.reader, None, started
        )
        plan = access.plan(state.request, guard())
        assert plan == state.native.plan
        raw = MapArtifactReader(plan, c.workspace, access).read(
            state.native.handle, "state.json", guard()
        )
        assert hashlib.sha256(raw).hexdigest() == state.native.file.sha256
        assert (
            len(c.sql.calls) == closed_queries > 0
        )  # Original state guard, no new SQL on readonly.
        with pytest.raises(OwnershipConflict):
            access.verify(plan, "write", guard())
    finally:
        c.close_sockets()
