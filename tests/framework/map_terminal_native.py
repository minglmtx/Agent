"""Actual final browser facts -> eligible original requests -> fixed DB capture."""

from datetime import datetime, timezone
from typing import Any
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_navigation_terminal_native import collect_navigation
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.sites.map.reference_authority import (
    MapReferenceAuthority,
)
from lab_generate_skill.bootstrap.map_terminal_evidence import (
    read_map_terminal_evidence,
)
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from lab_generate_skill.sites.map.terminal_requests import reference_candidates
from lab_generate_skill.sites.map.reference_selection import select_reference
from lab_generate_skill.sites.map.evidence_schema import MapCapturePair
from map_qualified_source_native import MapQualifiedSource
from map_preparation_native import MapPreparation
from map_browser_capture_native import capture as browser_capture
from map_site_capture_native import (
    inspection,
    capture as site_capture,
    MapCaptureAuthority,
)
from browser_resource_fixtures import ResourceCase


def collect(
    source: MapQualifiedSource,
    browser: ResourceCase,
    session: EvidenceBrowserSession,
    *,
    actor: dict[str, Any] | None = None,
) -> None:
    n = source.native
    assert isinstance(n, MapPreparation)
    if isinstance(n.overlay_spec, NavigationSpec):
        collect_navigation(source, browser, session, actor)
        return
    if n.inputs.original_reference_ref is None:
        raise ValueError("Original MapData complete reference declaration required")
    final = browser_capture(browser, session, "map-native-process")
    selected = MapTerminalSelection(
        initial=source.saved["initial_selection"],
        capture_intent_ref=final.intent_ref,
        capture_result_ref=final.result_ref,
        original_reference_ref=n.inputs.original_reference_ref,
    )
    terminal_ref = n.put(selected)
    source.saved["map_terminal_ref"] = terminal_ref
    source.saved["map_page"] = browser_capture(browser, session, "map-page-health")
    op = browser.op.cleanup(
        "selected-map-terminal-read", now=datetime.now(timezone.utc), seconds=600
    )
    control = browser.controls.bind(op)

    def read(ref: EvidenceRef, current: OperationControl) -> TerminalMapEvidence:
        return read_map_terminal_evidence(
            source.c.evidence, n.records, ref, op, current
        )

    terminal = read(terminal_ref, control)
    candidates = reference_candidates(terminal, control)
    source.saved["map_request_selection"] = dict(
        eligible=[
            dict(
                index=v.index,
                request_id=v.request_id,
                response_kind=v.response_kind,
                bounds=v.bounds,
            )
            for v in candidates.selected
        ],
        skipped=list(candidates.skipped),
    )
    authority = MapReferenceAuthority(
        MapCaptureAuthority(source), source.c.evidence, read
    )
    pairs: list[MapCapturePair] = []
    source.saved["map_reference_returns"] = pairs
    # No eligible request means exactly zero database dispatch. The list is set
    # only after all required requests returned; partial capture stays unknown.
    for candidate in candidates.selected:
        request = inspection(source, f"selected-map-reference-{candidate.index}")
        reference = select_reference(
            terminal_ref, terminal, request, candidate.index, source.c.evidence, control
        )
        pairs.append(
            site_capture(
                source,
                SiteCaptureRequest(
                    inspection=request,
                    collector_id="map-native-reference",
                    collector_version="1",
                    selection_ref=n.put(reference),
                ),
                authority,
            )
        )
    source.saved["map_references"] = tuple(pairs)
