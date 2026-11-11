"""Actual full files on the existing ports, with explicit synthetic authority."""

import hashlib
from pathlib import Path
from site_instance_fixtures import node_path as node_path
from typing import Any
import pytest
import lab_generate_skill.adapters.map_artifacts.writer as physical
from lab_generate_skill.adapters.map_artifacts.files import write_once
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.adapters.map_artifacts.state_reader import (
    OriginalMapStateReader,
)
from lab_generate_skill.adapters.map_artifacts.state_publisher import MapStatePublisher
from lab_generate_skill.adapters.map_artifacts.site_plan import original_site_plan
from lab_generate_skill.bootstrap.map_database_publisher import MapDatabasePublisher
from lab_generate_skill.sites.map.native_route_collector import (
    MapNativeRequestCollector,
)
from lab_generate_skill.sites.map.native_surface_capture import NativeSurfaceCapture
from lab_generate_skill.sites.map.native_notes_capture import NativeNotesCapture
from lab_generate_skill.sites.map.native_served_capture import NativeServedCapture
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.map_navigation_artifact import MapNavigationArtifactPlan
from lab_generate_skill.domain.map_private_artifact import parse_map_artifact_plan
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_file_fixtures import navigation_files, DeclaredFilePermission
from map_navigation_fixtures import SOURCES
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_navigation_complete_file_roundtrip_and_small_native_state_reference(
    node_path: Path, source: str
) -> None:
    c = navigation_files(node_path, source)
    authority = DeclaredFilePermission(c)
    publisher = MapStatePublisher(c.workspace, authority, authority)
    # A 64MiB+ native file must use full-file publication, never a small CAS body.
    raw = b"full native state byte\n" * (64 * 1024**2 // 22 + 1)
    assert len(raw) > 64 * 1024**2
    result = publisher.publish(c.request, raw, "a" * 64, guard())
    assert isinstance(result.plan, MapNavigationArtifactPlan)
    assert len(result.model_dump_json().encode()) < 8192
    assert result.file.size_bytes == len(raw)
    assert result.file.sha256 == hashlib.sha256(raw).hexdigest()
    assert MapStateArtifact.model_validate_json(result.model_dump_json()) == result
    authority.read_only = True
    reader = OriginalMapStateReader(c.workspace, authority, authority)
    assert reader.read(result, c.request, guard()) == raw
    assert publisher.writers[0].state == "sealed"
    with pytest.raises(InvalidTransition):
        publisher.publish(c.request, raw, "a" * 64, guard())
    assert len(publisher.writers) == 1
    with pytest.raises(PermissionError):
        authority.verify(result.plan, "write", guard())


@pytest.mark.parametrize("field", ["task", "attempt", "private", "allocation"])
def test_navigation_plan_rejects_changed_request_before_file_effects(
    node_path: Path, field: str
) -> None:
    c = navigation_files(node_path)
    raw = c.request.model_dump()
    if field == "task":
        raw["task"]["task_id"] = "wrong-task"
    elif field == "private":
        raw["private_input"] += " "
    elif field == "attempt":
        raw["operation"]["attempt_id"] = "wrong-attempt"
    else:
        raw["operation"]["allocation_id"] = "wrong-allocation"
    request = SiteTaskRequest.model_validate(raw)
    with pytest.raises(OwnershipConflict):
        original_site_plan(c.configuration, request)
    assert not tuple((c.workspace / "navigation-files").iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "map-private-artifact-plan/1"),
        ("schema_version", "arbitrary/1"),
        ("native_contract_sha256", "a" * 64),
        ("native_contract_sha256", None),
        ("producer", "browser_process"),
        ("max_files", True),
        ("max_file_bytes", 0),
        ("private_root", "/outside-workspace"),
        ("private_root", "relative"),
        ("private_root", None),
    ],
)
def test_navigation_concrete_plan_never_uses_old_or_unknown_schema(
    node_path: Path, field: str, value: Any
) -> None:
    c = navigation_files(node_path)
    plan = original_site_plan(c.configuration, c.request)
    raw = plan.model_dump()
    raw[field] = value
    with pytest.raises(ValueError):
        parse_map_artifact_plan(raw)
    assert not tuple((c.workspace / "navigation-files").iterdir())


@pytest.mark.parametrize("phase", ["initialize", "write", "seal"])
def test_navigation_partial_or_cancelled_publication_preserves_first_failure_no_retry(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    c = navigation_files(node_path)
    authority = DeclaredFilePermission(c)
    publisher = MapStatePublisher(c.workspace, authority, authority)
    first = TimeoutError("synthetic cancellation/partial file at " + phase)
    verify = authority.verify
    physical_write = write_once

    def fail_at_phase(plan: Any, action: Any, control: OperationControl) -> None:
        verify(plan, action, control)
        if action == phase and phase != "write":
            raise first

    def partial_file(
        root: Path, name: str, data: bytes, control: OperationControl, **kwargs: Any
    ) -> Any:
        if phase == "write" and name == "state.json":
            (root / name).write_bytes(data[:3])
            raise first
        return physical_write(root, name, data, control, **kwargs)

    monkeypatch.setattr(authority, "verify", fail_at_phase)
    monkeypatch.setattr(physical, "write_once", partial_file)
    with pytest.raises(TimeoutError) as caught:
        publisher.publish(c.request, b"complete bytes required", "a" * 64, guard())
    assert caught.value is first and publisher.error is first
    assert publisher.state == "failed" and not publisher.results
    writer = publisher.writers[0]
    if phase == "write":
        assert (writer.working / "state.json").read_bytes() == b"com"
    with pytest.raises(InvalidTransition):
        publisher.publish(c.request, b"complete bytes required", "a" * 64, guard())
    assert len(publisher.writers) == 1


def test_navigation_manifest_wrong_plan_is_not_read_and_no_MapData_query(
    node_path: Path,
) -> None:
    c = navigation_files(node_path)
    authority = DeclaredFilePermission(c)
    publisher = MapStatePublisher(c.workspace, authority, authority)
    result = publisher.publish(c.request, b"actual state", "a" * 64, guard())
    other = parse_map_artifact_plan(
        {**result.plan.model_dump(), "artifact_id": "wrong-artifact"}
    )
    with pytest.raises(EvidenceIntegrityError):
        MapArtifactReader(other, c.workspace, authority).read(
            result.handle, result.file.path, guard()
        )

    # The database publisher's own boundary refuses navigation before any plan,
    # guard, writer or query. No actual native object is constructed by the double.
    class Access:
        inputs = c.inputs

        def plan(self, *args: Any) -> Any:
            pytest.fail("Navigation attempted a MapData file/query dispatch")

    access: Any = Access()
    native: Any = object()
    db = MapDatabasePublisher(access, native, native, native)
    with pytest.raises(ValueError, match="cannot dispatch navigation"):
        db.publish(native, native, guard())
    assert not db.writers and not db.captures


@pytest.mark.parametrize("collector", ["requests", "surface", "notes", "served"])
def test_mapdata_collectors_refuse_navigation_plan_before_native_effects(
    node_path: Path, collector: str
) -> None:
    c = navigation_files(node_path)
    plan = original_site_plan(c.configuration, c.request)
    unused: Any = object()
    with pytest.raises(ValueError):
        if collector == "requests":
            MapNativeRequestCollector(plan, unused)
        elif collector == "surface":
            NativeSurfaceCapture(plan, unused, guard())
        elif collector == "notes":
            NativeNotesCapture(plan, unused, guard(), "http://127.0.0.1:12001")
        else:
            NativeServedCapture(
                plan, unused, guard(), "http://127.0.0.1:12001", {}, "invalid"
            )
    assert not tuple((c.workspace / "navigation-files").iterdir())
