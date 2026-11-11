"""Original response files and pins are re-read; no trust in a passed flag alone."""

import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.bootstrap.map_served_evidence import map_reviewed_frontend
from map_registered_worker_fixtures import RegisteredMapCase
from map_terminal_fixtures import terminal
from map_terminal_request_fixtures import read_original
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    ["none", "body", "renderer", "source-pin", "frame", "status", "readout", "close"],
)
def test_original_served_files_recomputed(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with terminal(registered_map, monkeypatch) as c:
        b = c.initial.browser
        assert b.collector is not None
        raw, files = read_original(c)
        import json

        summary = json.loads(files.data["map-actually-served.json"])
        if fault == "body":
            files.data["map-served-0.js"] += b"broken full source"
        if fault == "renderer":
            summary["actual_renderer_functions"]["buildFeatures"] = "other"
        if fault == "source-pin":
            summary["original_source_pins"]["browse.js"] = "f" * 64
        if fault == "frame":
            summary["responses"][0]["original_main_frame"] = False
        if fault == "status":
            summary["responses"][0]["http_status"] = True
        if fault == "readout":
            summary["original_readout"]["observation"]["sequence"] = 99
        if fault == "close":
            files.change("map-served-close.json", pending_body_retained=True)
        files.change("map-actually-served.json", **summary)
        b.participant = "controller"
        try:
            if fault == "none":
                assert map_reviewed_frontend(files.evidence(raw), guard())
            else:
                with pytest.raises(EvidenceIntegrityError):
                    map_reviewed_frontend(files.evidence(raw), guard())
        finally:
            b.participant = "worker"


def test_no_eligible_request_requires_no_database_query(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from map_overlay_capture_fixtures import full_surface_fixture
    from lab_generate_skill.sites.map.overlay_evidence import original_overlay_checks
    from lab_generate_skill.sites.map.page_health import MapPageHealth
    from test_map_page_health import health

    full_surface_fixture(monkeypatch)
    with terminal(registered_map, monkeypatch) as c:
        raw, files = read_original(c)
        b = c.initial.browser
        before = list(registered_map.case.commands.calls)
        b.participant = "controller"
        try:
            source = files.evidence(raw)
            served = map_reviewed_frontend(source, guard())
            checks = original_overlay_checks(
                source,
                (),
                MapPageHealth.model_validate(health(b.page.url)),
                served=served,
                control=guard(),
            )
        finally:
            b.participant = "worker"
        assert (
            checks["valid_terminal_document"]
            and checks["actual_reviewed_frontend_served"]
        )
        assert not checks["actual_local_response_valid"]
        assert registered_map.case.commands.calls == before
