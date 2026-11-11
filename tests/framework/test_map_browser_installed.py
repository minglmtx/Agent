"""Installed original worker/Chromium/file authority; controlled page, no Map website."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import pytest
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.browsergym.storage_original import (
    OriginalBrowserAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.browser_access import (
    OriginalMapBrowserAccess,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.map_initial_capture import MapInitialCapture
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import InvalidTransition
from browser_resource_fixtures import ResourceCase, resource_case
from browser_worker_fixtures import configuration
from map_artifact_fixtures import case as file_case
from map_browser_storage_fixtures import collection_spec
from map_native_notes_actual import notes_document
from map_native_route_actual import server_fixture
from map_served_fixtures import TILES
from test_browser_resource_installed import EngineeringTreeAuthority
from test_browser_resource import enter, inspect
from test_browser_capture import Authority
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard
from storage_installation_fixtures import storage_installation
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from source_review_records import review_resource, ReadOnlyEvidence


def selected_resource(
    root: Path,
    patch: pytest.MonkeyPatch,
    url: str,
    installed: InstalledFixture | None,
    *,
    after_acquisition: bool = False,
) -> ResourceCase:
    root.chmod(0o700)
    config = configuration(
        storage_installation(installed) if installed is not None else None, url
    )
    if installed is not None:
        execution, _ = actual_slurm_execution()
        owner = config.spec.scope.owner.model_copy(update={"job_id": execution.job_id})
        config = config.model_copy(
            update={
                "spec": config.spec.model_copy(
                    update={
                        "scope": config.spec.scope.model_copy(update={"owner": owner})
                    }
                )
            }
        )
    else:
        owner = config.spec.scope.owner.model_copy(update={"job_id": "4752096"})
        config = config.model_copy(
            update={
                "spec": config.spec.model_copy(
                    update={
                        "scope": config.spec.scope.model_copy(update={"owner": owner})
                    }
                )
            }
        )
    c = resource_case(root, patch, config=config, real_step=installed is not None)
    c.op = c.op.model_copy(
        update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=180)}
    )
    template, _ = file_case(root, max_files=256)
    scope = template.plan.scope.model_copy(update={"owner": c.spec.token.owner})
    plan = MapPrivateArtifactPlan.model_validate(
        template.plan.model_copy(update={"scope": scope, "token": c.spec.token})
    )
    public = PublicTask(
        identity=scope.task,
        goal="Exercise controlled original MapData collection",
        start_url=url,
        allowed_actions=("click", "send_msg_to_user"),
    )
    session = BrowserSessionSpec.model_validate(
        config.spec.model_copy(update={"scope": scope, "task": public})
    )
    collection = collection_spec(root, c.op, TILES)
    if after_acquisition:
        collection = collection.model_copy(
            update={
                "lifetime_operation": collection.lifetime_operation.model_copy(
                    update={"deadline": c.op.deadline + timedelta(seconds=300)}
                )
            }
        )
    inputs = MapBrowserInputs(
        plan=plan,
        evidence_root=str(root / "evidence"),
        resource_journal_root=str(root / "journal"),
        collection=collection,
    )
    config = BrowserWorkerConfiguration.model_validate(
        config.model_copy(update={"spec": session, "map_inputs": inputs})
    )
    c.spec = BrowserResourceSpec.model_validate(
        c.spec.model_copy(update={"configuration": config})
    )
    if installed is not None:
        patch.setattr(
            "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
            FramedProcessSession,
        )
        c.authority = EngineeringTreeAuthority(c.evidence)
    return c


def test_installed_map_collection_fixture_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.sites.map.browser_collection import MapBrowserCollection
    from lab_generate_skill.adapters.browsergym.collection_control import (
        OriginalMapCollectionControl,
    )
    from browsergym_fixtures import LoopbackAuthority
    from test_site_storage_admission import LiveGuard
    from generator_worker_fixtures import unit_guard

    c = selected_resource(tmp_path, monkeypatch, "http://127.0.0.1:8000/", None)
    engine = build_browser_engine(
        c.spec.configuration,
        LoopbackAuthority(),
        SystemClock(),
        worker_guard=LiveGuard(unit_guard(c.spec.slurm.parent.writer, guard())),
    )
    assert isinstance(engine.process_collector, MapBrowserCollection)
    assert engine.collector is engine.process_collector and engine.state == "new"
    inputs = c.spec.configuration.map_inputs
    assert inputs is not None and inputs.collection.operation == c.op
    lifetime = engine.process_collector.lifetime
    assert isinstance(lifetime, OriginalMapCollectionControl)
    assert lifetime.operation == inputs.collection.lifetime_operation
    assert inputs.collection.lifetime_operation.operation_id != c.op.operation_id
    assert inputs.collection.tile_origin == TILES
    document, assets = notes_document()
    assert b"triggerOriginalNotes" in document and len(assets) == 5
    assert not Path(inputs.plan.private_root).exists()
    assert not c.channels


@pytest.mark.parametrize(
    "initialization", ["public", "native", "native-after-acquisition"]
)
def test_installed_map_original_worker_capture_and_independent_files(
    installed_sources: InstalledFixture,
    initialization: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from map_initialization_actual_fixtures import (
        readiness_document,
        bind_native,
        DOCUMENT_TARGET,
    )

    document, assets = (
        readiness_document()
        if initialization.startswith("native")
        else notes_document()
    )
    with server_fixture(
        "batch",
        document=document,
        assets=assets,
        document_target=(
            DOCUMENT_TARGET if initialization.startswith("native") else None
        ),
    ) as fixture:
        c = selected_resource(
            tmp_path,
            monkeypatch,
            fixture.origin + "/",
            installed_sources,
            after_acquisition=initialization == "native-after-acquisition",
        )
        if initialization.startswith("native"):
            bind_native(c, fixture.origin + "/")
        initial_capture: MapInitialCapture | None = None
        with enter(c) as browser:
            assert isinstance(browser.engine, SupervisedBrowserSession)
            client = browser.engine
            initial = client.last_readout
            assert initial is not None and initial.observation.sequence == 0
            inputs = c.spec.configuration.map_inputs
            assert inputs is not None
            # Original installed collector had to acquire write permission before goto.
            assert (
                Path(inputs.plan.private_root) / "working/map-collection-intent.json"
            ).is_file()
            assert fixture.documents == 1 and not fixture.native_calls
            if initialization.startswith("native"):
                request0 = BrowserCaptureRequest(
                    scope=client.spec.scope,
                    operation=c.op.model_copy(
                        update={"operation_id": "initial-native-private"}
                    ),
                    observation_sha256=hashlib.sha256(
                        initial.observation.model_dump_json().encode()
                    ).hexdigest(),
                    collector_id="map-initial-readiness",
                    collector_version="1",
                )
                capture0 = RecordedBrowserCapture(
                    client, c.evidence, Authority(c.evidence)
                )
                capture0.capture(request0, control=guard(30))
                assert capture0.result is not None
                initial_capture = MapInitialCapture.model_validate_json(
                    capture0.result.private_result
                )
                assert (
                    client.last_readout is initial
                    and initial_capture.readout_sha256
                    == hashlib.sha256(initial.model_dump_json().encode()).hexdigest()
                )
                assert not (
                    Path(inputs.plan.private_root) / "published/manifest.json"
                ).exists()
                assert (
                    fixture.documents == 1
                    and not fixture.native_calls
                    and fixture.note_calls == 0
                )
            action_operation = c.op
            if initialization == "native-after-acquisition":
                # Exercise the original 180-second boundary with a real worker.
                # No command or caller may renew the separately pinned lifetime.
                while True:
                    remaining = (
                        c.op.deadline - datetime.now(timezone.utc)
                    ).total_seconds()
                    if remaining < 0:
                        break
                    time.sleep(min(10.0, remaining + 0.1))
                assert c.op.deadline < datetime.now(timezone.utc)
                assert (
                    datetime.now(timezone.utc)
                    < inputs.collection.lifetime_operation.deadline
                )
                action_operation = c.op.model_copy(
                    update={
                        "deadline": datetime.now(timezone.utc) + timedelta(seconds=120)
                    }
                )
            button = re.search(
                r"\[([^\]]+)\] button ['\"]Fetch Map Data['\"]",
                initial.observation.text or "",
            )
            assert button, initial.observation.text
            browser.step(
                BrowserAction(
                    action_id="native",
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload=f"click({button.group(1)!r})",
                ),
                action_operation.model_copy(update={"operation_id": "native-click"}),
                control=guard(60),
            )
            browser.step(
                BrowserAction(
                    action_id="terminal",
                    protocol_id="browsergym-highlevel-v1",
                    name="send_msg_to_user",
                    payload="send_msg_to_user('done')",
                ),
                action_operation.model_copy(update={"operation_id": "native-terminal"}),
                control=guard(60),
            )
            final = client.last_readout
            assert (
                final is not None
                and final.observation.sequence == 2
                and final.protocol_terminal
            )
            request = BrowserCaptureRequest(
                scope=client.spec.scope,
                operation=action_operation.model_copy(
                    update={"operation_id": "terminal-file-capture"}
                ),
                observation_sha256=hashlib.sha256(
                    final.observation.model_dump_json().encode()
                ).hexdigest(),
                collector_id="map-native-process",
                collector_version="1",
            )
            capture = RecordedBrowserCapture(client, c.evidence, Authority(c.evidence))
            result_ref = capture.capture(request, control=guard(60))
            assert capture.result is not None
            publication = MapBrowserPublication.model_validate_json(
                capture.result.private_result
            )
            assert client.last_readout is final and publication.sequence == 2
            with pytest.raises(InvalidTransition):
                capture.capture(request, control=guard())
            assert (
                len(fixture.native_calls) == 3
                and fixture.note_calls == 1
                and fixture.documents == 1
            )
            for _, headers in fixture.native_calls:
                assert "cookie" not in headers and "authorization" not in headers
        record = inspect(c)
        assert record.state == "closed" and [
            event.state for event in record.events
        ] == ["registered", "acquiring", "acquired", "closing", "closed"]
        closed = json.loads(c.evidence.read(record.events[-1].evidence[0]))["details"]
        assert closed["cleanup_errors"] == []
        reviewed = review_resource(
            record.model_dump(mode="json"),
            c.spec.token,
            ReadOnlyEvidence(tmp_path / "evidence"),
            guard(30),
        )
        access = OriginalMapBrowserAccess(
            c.spec.configuration, "controller", OriginalBrowserAcquisitionReader(), None
        )
        reader = MapArtifactReader(
            inputs.plan, Path(inputs.plan.workspace_root), access
        )
        manifest = reader.manifest(publication.handle, guard(30))
        assert (
            reader.read(
                publication.handle, publication.terminal_readout.path, guard(30)
            )
            == final.model_dump_json().encode()
        )
        process_end = json.loads(
            reader.read(publication.handle, "map-process-close.json", guard(30))
        )
        assert (
            process_end["original_relay_physical_closed"] is True
            and process_end["request_count"] == 1
        )
        assert (
            process_end["unique_readout_count"] == 3
            and not process_end["cleanup_errors"]
        )
        readiness = None
        if initialization.startswith("native"):
            readiness_raw = reader.read(
                publication.handle, "map-initial-readiness.json", guard(30)
            )
            assert (
                initial_capture is not None
                and readiness_raw == initial_capture.readiness_json.encode()
            )
            readiness = json.loads(readiness_raw)
            assert (
                readiness["stable_seconds"] >= 0.75
                and readiness["native_readiness"]["ready"] is True
            )
            assert readiness["native_view"]["native_geo_uri"] == "geo:40.77,-73.97?z=14"
            assert readiness[
                "public_task"
            ] == c.spec.configuration.spec.task.model_dump(mode="json")
            assert (
                not readiness["new_observation_created"]
                and not readiness["task_success_or_admission_claim"]
            )
            manifest_paths = {f.path for f in manifest.artifact.files}
            assert "map-initial-readiness-failure.json" not in manifest_paths
        report = {
            "initialization": initialization,
            "acquisition_expired_before_actions": initialization
            == "native-after-acquisition",
            "original_acquisition_deadline": inputs.collection.operation.deadline.isoformat(),
            "original_collection_deadline": inputs.collection.lifetime_operation.deadline.isoformat(),
            "original_initial_readiness": readiness,
            "initial_capture": (
                initial_capture.model_dump(mode="json")
                if initial_capture is not None
                else None
            ),
            "schema_version": "map-installed-collection-check/1",
            "task_website_or_actor_claim": False,
            "configuration": c.spec.configuration.model_dump(mode="json"),
            "publication": publication.model_dump(mode="json"),
            "capture_ref": result_ref.model_dump(mode="json"),
            "resource_target": reviewed["target"],
            "states": [event.state for event in record.events],
            "closure_details": closed,
            "files": len(manifest.artifact.files),
            "full_bytes": sum(f.size_bytes for f in manifest.artifact.files),
            "document_gets": fixture.documents,
            "native_gets": len(fixture.native_calls),
            "notes_gets": fixture.note_calls,
            "unique_return_sequences": [0, 1, 2],
            "original_relay_physically_closed": True,
            "independent_original_file_readback": True,
        }
        output = (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "map-installed-collection.json"
        )
        output.write_text(json.dumps(report, indent=2) + "\n")
