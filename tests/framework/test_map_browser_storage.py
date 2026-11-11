"""Frozen original browser ownership -> complete file publication/readback, no Actor."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any, Literal
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_storage_original import BrowserStorageOriginal
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.domain.map_private_artifact import MapArtifactHandle
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    OperationStopped,
    EvidenceIntegrityError,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from map_browser_storage_fixtures import BrowserFilesCase
from browser_worker_fixtures import UnitBrowser, configuration
from test_browser_resource import enter, inspect
from test_slurm_commands import guard


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrowserFilesCase:
    return BrowserFilesCase(tmp_path, monkeypatch)


def test_original_acquisition_before_navigation_and_cross_thread_files(
    c: BrowserFilesCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = UnitBrowser.start
    calls: list[str] = []

    def first(engine: UnitBrowser, *args: Any, **kwargs: Any) -> Any:
        original = c.reader.read(c.configuration, guard())
        assert original.record.state == "acquired" and engine.last_readout is None
        assert original.acquired.details.browser_started is False
        calls.append("before-native-start")
        return start(engine, *args, **kwargs)

    monkeypatch.setattr(UnitBrowser, "start", first)
    with enter(c.resource):
        authority = c.authority()
        writer = c.writer(authority)
        writer.initialize(guard())
        with ThreadPoolExecutor(max_workers=2) as threads:
            results = list(
                threads.map(
                    lambda i: writer.retain(
                        f"native-{i}.bin", bytes([i]) * 2048, guard()
                    ),
                    range(4),
                )
            )
        assert len(results) == 4 and writer.total == 8192
        with pytest.raises(InvalidTransition):
            writer.retain("native-0.bin", b"overwrite", guard())
        handle = writer.seal(guard())
        with pytest.raises(InvalidTransition):
            writer.seal(guard())
        assert calls == ["before-native-start"]
    assert inspect(c.resource).state == "closed"
    with pytest.raises(OwnershipConflict):
        authority.verify(c.plan, "read", guard())
    c.participant = "controller"
    reader_authority = c.authority()
    reader = MapArtifactReader(c.plan, Path(c.plan.workspace_root), reader_authority)
    assert len(reader.manifest(handle, guard()).artifact.files) == 4
    with pytest.raises(OwnershipConflict):
        reader_authority.verify(c.plan, "write", guard())


@pytest.mark.parametrize("phase", ["initialize", "seal"])
def test_only_original_owner_thread_initializes_and_seals(
    c: BrowserFilesCase, phase: Literal["initialize", "seal"]
) -> None:
    with enter(c.resource):
        authority = c.authority()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict, match="owner thread"):
                pool.submit(authority.verify, c.plan, phase, guard()).result()


@pytest.mark.parametrize(
    "fault", ["identity", "physical", "guard", "plan", "stopped", "cancel"]
)
def test_mismatch_and_cancellation_refuse_new_file(
    c: BrowserFilesCase, fault: str
) -> None:
    with enter(c.resource):
        authority = c.authority()
        writer = c.writer(authority)
        writer.initialize(guard())
        if fault == "identity":
            c.identity_changed = True
        elif fault == "physical":
            c.member_change["task_inode"] = 1
        elif fault == "guard":
            assert authority.worker_guard is not None
            from test_site_storage_admission import LiveGuard

            value = c.reader.read(
                c.configuration, guard()
            ).acquired.details.prepared.owner_guard
            authority.worker_guard = LiveGuard(
                value.model_copy(
                    update={
                        "worker": value.worker.model_copy(update={"start_ticks": 999})
                    }
                )
            )
        elif fault == "plan":
            writer.plan = writer.plan.model_copy(update={"artifact_id": "foreign"})
        elif fault == "stopped":
            authority.stop_new_io()
        control = guard(0.000001) if fault == "cancel" else guard()
        if fault == "cancel":
            import time

            time.sleep(0.002)
        with pytest.raises((OwnershipConflict, InvalidTransition, OperationStopped)):
            writer.retain("denied.bin", b"no write", control)
        assert not (writer.working / "denied.bin").exists()


@pytest.mark.parametrize("participant", ["worker", "controller"])
def test_worker_observer_mount_id_only_may_differ(
    c: BrowserFilesCase, participant: Literal["worker", "controller"]
) -> None:
    with enter(c.resource):
        c.participant = participant
        authority = c.authority()
        original = c.reader.read(c.configuration, guard())
        member = (
            original.acquired.details.prepared.step.controller.target.worker
            if participant == "worker"
            else original.spec.slurm.parent
        )
        c.member_change["mount_id"] = member.mount_id + 100
        if participant == "worker":
            authority.verify(c.plan, "read", guard())
        else:
            with pytest.raises(OwnershipConflict, match="physical"):
                authority.verify(c.plan, "read", guard())


def test_missing_acquisition_and_changed_frozen_configuration_rejected(
    c: BrowserFilesCase,
) -> None:
    with pytest.raises(EvidenceIntegrityError):
        c.reader.read(c.configuration, guard())
    with enter(c.resource):
        config = c.configuration.model_copy(
            update={"spec": c.configuration.spec.model_copy(update={"seed": 17})}
        )
        with pytest.raises(OwnershipConflict, match="configuration"):
            c.reader.read(config, guard())
        original = c.reader.read(c.configuration, guard())
        changed = original.model_dump(mode="json")
        changed["acquired"]["operation"]["parent_operation_id"] = "other-parent"
        with pytest.raises(OwnershipConflict):
            BrowserStorageOriginal.model_validate_json(json.dumps(changed))


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_root", ""),
        ("evidence_root", None),
        ("evidence_root", 1),
        ("evidence_root", "/outside"),
        ("resource_journal_root", "/tmp/../alias"),
    ],
    ids=["empty", "null", "wrong-type", "outside", "alias"],
)
def test_input_roots_reject_invalid(
    c: BrowserFilesCase, field: str, value: Any
) -> None:
    assert c.configuration.map_inputs is not None
    data = c.configuration.map_inputs.model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        MapBrowserInputs.model_validate_json(json.dumps(data))


def test_roots_overlap_map_missing_or_other_site_and_old_config_rejected(
    c: BrowserFilesCase,
) -> None:
    assert c.configuration.map_inputs is not None
    inputs = c.configuration.map_inputs
    for path in (
        inputs.evidence_root,
        inputs.evidence_root + "/nested",
        inputs.plan.private_root,
    ):
        with pytest.raises(ValidationError):
            MapBrowserInputs.model_validate(
                inputs.model_copy(update={"resource_journal_root": path})
            )
    for changed in (
        c.configuration.model_copy(update={"map_inputs": None}),
        configuration().model_copy(update={"map_inputs": inputs}),
        c.configuration.model_copy(
            update={"schema_version": "browser-worker-configuration/2"}
        ),
    ):
        with pytest.raises(ValidationError):
            BrowserWorkerConfiguration.model_validate(changed)
    token = c.resource.spec.token.model_copy(update={"allocation_id": "different"})
    with pytest.raises(ValidationError, match="token"):
        BrowserResourceSpec.model_validate(
            c.resource.spec.model_copy(update={"token": token})
        )


def test_original_closing_allows_final_retention_and_seal_but_no_new_collection(
    c: BrowserFilesCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = UnitBrowser.close
    handles: list[MapArtifactHandle] = []
    writer = None
    authority = None

    def finish(engine: UnitBrowser, *args: Any, **kwargs: Any) -> Any:
        assert inspect(c.resource).state == "closing"
        assert writer is not None and authority is not None
        with pytest.raises(OwnershipConflict, match="initialize"):
            authority.verify(c.plan, "initialize", guard())
        writer.retain("original-close.json", b'{"closed":true}', guard())
        handles.append(writer.seal(guard()))
        return close(engine, *args, **kwargs)

    monkeypatch.setattr(UnitBrowser, "close", finish)
    with enter(c.resource):
        authority = c.authority()
        writer = c.writer(authority)
        writer.initialize(guard())
        writer.retain("native.bin", b"complete", guard())
    assert len(handles) == 1 and inspect(c.resource).state == "closed"
    c.participant = "controller"
    reader = MapArtifactReader(c.plan, Path(c.plan.workspace_root), c.authority())
    assert reader.read(handles[0], "original-close.json", guard()) == b'{"closed":true}'


def test_unselected_public_navigation_keeps_its_existing_contract() -> None:
    config = configuration()
    assert config.spec.task.identity.family != "native_route_map_data"
    assert config.map_inputs is None
    assert (
        BrowserWorkerConfiguration.model_validate_json(config.model_dump_json())
        == config
    )
