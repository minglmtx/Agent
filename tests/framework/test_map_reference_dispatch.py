"""Terminal -> SiteCapture wire -> fixed worker -> complete native DB file.

Real acquired journals/CAS/artifact authority/dispatch; explicit Page/kernel,
SQL guard and Rails output doubles. No real Map site or Actor claim.
"""

from decimal import Decimal
import traceback
import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.sites.map.reference_authority import (
    MapReferenceAuthority,
)
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.map_database_artifact import MapDatabaseArtifact
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.bootstrap.map_database_reference import map_database_reference
from lab_generate_skill.sites.map.reference_evidence import MapReferenceRead
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OperationStopped,
    EvidenceIntegrityError,
    OwnershipConflict,
)
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.native_database import DATABASE_VERSION
from lab_generate_skill.sites.map.reference_selection import select_reference
from map_terminal_fixtures import terminal
from map_overlay_capture_fixtures import full_surface_fixture
from test_map_browser_collection import capture as browser_capture
from test_map_page_health import health
from lab_generate_skill.sites.map.page_capture import PAGE_HEALTH_PROGRAM
from lab_generate_skill.sites.map.page_evidence import terminal_page_health
from lab_generate_skill.bootstrap.map_served_evidence import map_reviewed_frontend
from lab_generate_skill.sites.map.overlay_evidence import original_overlay_checks
from typing import Any
from map_terminal_request_fixtures import Requests, read_original
from map_registered_worker_fixtures import RegisteredMapCase
from preparation_record_fixtures import put
from test_site_capture import Authority
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "mode",
    [
        "native",
        "batch",
        "large",
        "unknown",
        "malformed",
        "protocol-native",
        "protocol-batch",
    ],
)
def test_terminal_selection_fixed_worker_full_reference_and_closed_read(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    protocol = mode.startswith("protocol-")
    mode = mode.removeprefix("protocol-")
    original = registered_map
    full_surface_fixture(monkeypatch)
    requests = Requests(monkeypatch, "batch" if mode == "batch" else "native")
    with terminal(
        original,
        monkeypatch,
        action="protocol" if protocol else "none",
        before_action=requests if protocol else None,
        before_capture=None if protocol else requests,
    ) as c:
        raw, files = read_original(c)
        store = original.resource.evidence
        inspection = original.request("inspect")
        selected = select_reference(
            c.reference, files.evidence(raw), inspection, 0, store, guard(60)
        )
        request = SiteCaptureRequest(
            inspection=inspection,
            collector_id="map-native-reference",
            collector_version="1",
            selection_ref=put(store, selected),
        )
        authority = MapReferenceAuthority(
            Authority(store), store, lambda ref, control: c.load()
        )
        verify = authority.verify_capture

        def controller_verification(
            configuration: SiteWorkerConfiguration,
            request: SiteCaptureRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            old_site, old_browser = original.observer, c.initial.browser.participant
            original.observer = c.initial.browser.participant = "controller"
            try:
                verify(configuration, request, intent_ref, control)
            finally:
                original.observer, c.initial.browser.participant = old_site, old_browser

        monkeypatch.setattr(authority, "verify_capture", controller_verification)
        body = json.dumps(
            dict(
                version=DATABASE_VERSION,
                bounds=list(selected.bounds),
                initial_node_ids=["1"],
                nodes=[
                    dict(
                        id="1",
                        version="1",
                        lat=format(
                            (
                                (
                                    Decimal(selected.bounds[1])
                                    + Decimal(selected.bounds[3])
                                )
                                / 2
                            ).quantize(Decimal("0.0000001")),
                            "f",
                        ),
                        lon=format(
                            (
                                (
                                    Decimal(selected.bounds[0])
                                    + Decimal(selected.bounds[2])
                                )
                                / 2
                            ).quantize(Decimal("0.0000001")),
                            "f",
                        ),
                        tags={},
                    )
                ],
                ways=[],
                relations=[],
            )
        ).encode()
        if mode == "malformed":
            body = b"{not-a-complete-native-reference"
        if mode == "large":
            body += b" " * (65 * 1024**2)
        commands = original.case.commands
        run = commands.run
        queries: list[tuple[str, ...]] = []

        def native(argv: tuple[str, ...], control: OperationControl) -> bytes:
            if "runner" not in argv:
                return run(argv, control)
            control.checkpoint()
            assert argv[-5:-1] == ("bundle", "exec", "rails", "runner")
            queries.append(argv)
            spec = original.case.spec
            directory = (
                Path(spec.state_root("frontend")) / "native-reference-layer-final-0"
            )
            path = directory / "osm-expanded-layer-final-0.json"
            assert (directory / "reference.rb").is_file()
            with path.open("xb") as stream:
                stream.write(body)
            path.chmod(0o400)
            if mode == "unknown":
                raise OSError(
                    "native query finished output but transport result unknown"
                )
            return b"native diagnostic is not the reference body"

        monkeypatch.setattr(commands, "run", native)
        original.observer = "worker"
        recorder = RecordedSiteCapture(c.initial.live.capture, store, authority)
        for change in (
            {"selection_ref": None},
            {"collector_id": "map-overlay-state"},
            {"selection_ref": "bad-type"},
        ):
            with pytest.raises(ValueError):
                SiteCaptureRequest.model_validate(request.model_copy(update=change))
        assert original.worker is not None
        with pytest.raises(OperationStopped):
            original.worker.capture_task(request, control=guard(-1))
        assert not queries
        if mode in ("unknown", "malformed"):
            with pytest.raises(SiteWorkerFailure):
                recorder.capture(request, control=guard(120))
            assert len(queries) == 1
            assert (
                original.worker.tasks is not None
                and original.worker.tasks.phase == "quarantined"
            )
            with pytest.raises(InvalidTransition):
                original.worker.capture_task(request, control=guard())
            assert len(queries) == 1
            return
        try:
            result_ref = recorder.capture(request, control=guard(120))
        except SiteWorkerFailure as error:
            print(error.reply.model_dump_json())
            if (
                original.worker.tasks is not None
                and original.worker.tasks.error is not None
            ):
                traceback.print_exception(original.worker.tasks.error)
            raise
        assert recorder.result is not None and recorder.intent_ref is not None
        artifact = MapDatabaseArtifact.model_validate_json(
            recorder.result.private_result
        )
        assert artifact.request == request and artifact.selected == selected
        assert artifact.output.size_bytes == len(body)
        assert artifact.output.sha256 == hashlib.sha256(body).hexdigest()
        assert result_ref.size_bytes < 65536 and len(queries) == 1
        assert artifact.before_sha256 == artifact.after_sha256
        started = c.initial.live.site.instance
        intent_ref = recorder.intent_ref
        b = c.initial.browser
        assert b.collector is not None
        evaluate_page = b.page.evaluate

        def health_read(program: str, args: Any = None) -> Any:
            return (
                health(b.page.url)
                if program == PAGE_HEALTH_PROGRAM
                else evaluate_page(program, args)
            )

        monkeypatch.setattr(b.page, "evaluate", health_read)
        health_recorder, health_request = browser_capture(b, c.initial.session)
        health_request = health_request.model_copy(
            update={
                "collector_id": "map-page-health",
                "operation": health_request.operation.model_copy(
                    update={"operation_id": "final-health"}
                ),
            }
        )
        health_result = health_recorder.capture(health_request, control=guard())
        assert health_recorder.intent_ref is not None
        health_intent = health_recorder.intent_ref

        def independent_read(
            selected_result: EvidenceRef = result_ref,
        ) -> MapReferenceRead:
            old_site, old_browser = original.observer, c.initial.browser.participant
            original.observer = c.initial.browser.participant = "controller"
            try:
                terminal_facts = c.load()
                result = map_database_reference(
                    store,
                    original.configuration,
                    started,
                    intent_ref,
                    selected_result,
                    terminal_facts,
                    guard(120),
                )
                page = terminal_page_health(
                    terminal_facts, store, health_intent, health_result, guard()
                )
                served = map_reviewed_frontend(terminal_facts, guard())
                if mode == "native":
                    invalid: Any
                    for invalid in ((), (result, result), (None,), None):
                        with pytest.raises(EvidenceIntegrityError):
                            original_overlay_checks(
                                terminal_facts,
                                invalid,
                                page,
                                served=served,
                                control=guard(120),
                            )
                checks = original_overlay_checks(
                    terminal_facts, (result,), page, served=served, control=guard(120)
                )
                assert (
                    checks["actual_reviewed_frontend_served"]
                    and checks["valid_terminal_document"]
                )
                assert checks["original_requested_native_route_preserved"]
                # Fixture transport is complete empty XML; independent DB has one
                # node. Preserve the real comparison failure, never a success sample.
                assert not checks["actual_local_response_valid"]
                return result
            finally:
                original.observer, c.initial.browser.participant = old_site, old_browser

        measured = independent_read()
        assert measured.database == body and measured.artifact == artifact
        assert measured.comparison["response_kind"] == selected.response_kind
        assert measured.comparison["provenance_verified"] is False
        assert measured.comparison["native_single_map_http200_claim"] is False
        assert len(queries) == 1
        bad_result = SiteTaskResult(
            request_sha256="f" * 64, private_result=recorder.result.private_result
        )
        with pytest.raises(OwnershipConflict):
            independent_read(put(store, bad_result))
        changed = artifact.model_copy(
            update={"output": artifact.output.model_copy(update={"sha256": "f" * 64})}
        )
        wrong = SiteTaskResult(
            request_sha256=request.digest, private_result=changed.model_dump_json()
        )
        with pytest.raises(EvidenceIntegrityError):
            independent_read(put(store, wrong))
        with pytest.raises(InvalidTransition):
            recorder.capture(request, control=guard())
        # New inspection IDs still refer to the same original terminal request.
        another = inspection.model_copy(
            update={
                "operation": inspection.operation.model_copy(
                    update={"operation_id": "second-reference"}
                )
            }
        )
        alternate = selected.model_copy(update={"inspection_sha256": another.digest})
        duplicate = request.model_copy(
            update={"inspection": another, "selection_ref": put(store, alternate)}
        )
        assert original.worker is not None and original.worker.references is not None
        with pytest.raises(InvalidTransition):
            original.worker.capture_task(duplicate, control=guard())
        assert len(queries) == 1
        started = c.initial.live.site.instance
    assert original.worker.closed
    original.observer = "controller"
    access = OriginalMapSiteAccess(
        original.configuration, "controller", original.reader, None, started
    )
    plan = access.plan(inspection, guard())
    assert plan == artifact.plan
    reader = MapArtifactReader(plan, original.workspace, access)
    assert reader.read(artifact.handle, artifact.output.path, guard(60)) == body
    assert len(queries) == 1

    independent = independent_read()
    assert independent == measured and len(queries) == 1
