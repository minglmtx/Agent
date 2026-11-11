"""Existing selected fixed DB capture with explicit native Rails output double."""

import json
import traceback
from decimal import Decimal
from pathlib import Path
import pytest
from lab_generate_skill.sites.map.reference_authority import (
    MapReferenceAuthority,
)
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.reference_selection import select_reference
from lab_generate_skill.sites.map.native_database import (
    DATABASE_VERSION,
    database_objects,
)
from lab_generate_skill.sites.map.native_bounds import Bounds
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.sites.map.evidence_schema import MapCapturePair
from map_terminal_fixtures import TerminalCase
from test_site_capture import Authority
from preparation_record_fixtures import put
from test_slurm_commands import guard


def capture_database(
    c: TerminalCase, patch: pytest.MonkeyPatch
) -> tuple[MapCapturePair, list[tuple[str, ...]]]:
    original, b = c.original, c.initial.browser
    store = original.resource.evidence
    original.observer = b.participant = "controller"
    inspection = original.request("inspect", "selected-final-reference")
    selected = select_reference(c.reference, c.load(), inspection, 0, store, guard(60))
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

    def controller(
        cfg: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        original.observer = b.participant = "controller"
        try:
            verify(cfg, request, ref, control)
        finally:
            original.observer = b.participant = "worker"

    patch.setattr(authority, "verify_capture", controller)
    body = database_body(selected.bounds)
    commands, queries = original.case.commands, []
    run = commands.run

    def native(argv: tuple[str, ...], control: OperationControl) -> bytes:
        if "runner" not in argv:
            return run(argv, control)
        queries.append(argv)
        path = (
            Path(original.case.spec.state_root("frontend"))
            / "native-reference-layer-final-0"
            / "osm-expanded-layer-final-0.json"
        )
        assert path.parent.joinpath("reference.rb").is_file()
        with path.open("xb") as stream:
            stream.write(body)
        path.chmod(0o400)
        return b"synthetic native runner diagnostic; full file retained"

    patch.setattr(commands, "run", native)
    original.observer = b.participant = "worker"
    recorder = RecordedSiteCapture(c.initial.live.capture, store, authority)
    try:
        result = recorder.capture(request, control=guard(60))
    except SiteWorkerFailure as error:
        print(error.reply.model_dump_json())
        if (
            original.worker is not None
            and original.worker.tasks is not None
            and original.worker.tasks.error is not None
        ):
            traceback.print_exception(original.worker.tasks.error)
        raise
    assert recorder.intent_ref is not None and len(queries) == 1
    return MapCapturePair(intent_ref=recorder.intent_ref, result_ref=result), queries


def database_body(bounds_value: Bounds) -> bytes:
    bounds = [Decimal(v) for v in bounds_value]
    body = json.dumps(
        dict(
            version=DATABASE_VERSION,
            bounds=list(bounds_value),
            initial_node_ids=["1"],
            nodes=[
                dict(
                    id="1",
                    version="1",
                    lat=format(
                        ((bounds[1] + bounds[3]) / 2).quantize(Decimal("0.0000001")),
                        "f",
                    ),
                    lon=format(
                        ((bounds[0] + bounds[2]) / 2).quantize(Decimal("0.0000001")),
                        "f",
                    ),
                    tags={},
                )
            ],
            ways=[],
            relations=[],
        )
    ).encode()
    database_objects(json.loads(body), bounds_value)  # Pure preflight before dispatch.
    return body
