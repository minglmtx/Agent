"""Current navigation callback binds original capture to the existing Actor trace."""

from datetime import datetime, timezone
from typing import Any
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.bootstrap.map_navigation_terminal import (
    read_map_navigation_terminal,
)
from lab_generate_skill.domain.map_navigation_terminal import (
    MapNavigationTerminalSelection,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.errors import IncompleteAnswerEvidence
from map_qualified_source_native import MapQualifiedSource
from browser_resource_fixtures import ResourceCase
from map_browser_capture_native import capture


def collect_navigation(
    source: MapQualifiedSource,
    browser: ResourceCase,
    session: EvidenceBrowserSession,
    actor: dict[str, Any] | None,
) -> None:
    final = capture(browser, session, "map-navigation-page-health")
    source.saved["map_page"] = final
    if (
        actor is None
        or actor.get("trace_ref") is None
        or actor.get("trace_snapshot_ref") is None
    ):
        raise IncompleteAnswerEvidence(
            "Original navigation sealed Actor trace unavailable"
        )
    op = browser.op.cleanup(
        "selected-navigation-terminal-read", now=datetime.now(timezone.utc), seconds=600
    )
    control = browser.controls.bind(op)
    n = source.native
    trace_ref = EvidenceRef.model_validate(actor["trace_ref"])
    trace = InteractionTrace.model_validate_json(
        source.c.evidence.read(trace_ref, control=control)
    )
    initial = InitialObservationReader(source.c.evidence, n.records).load(
        source.saved["initial_selection"], op, control
    )
    returned = initial.acquired.details.started.initial_return_ref
    for turn in trace.turns:
        if turn.interaction is not None and turn.interaction.result is not None:
            returned = turn.interaction.result.return_ref
    selected = MapNavigationTerminalSelection(
        initial=source.saved["initial_selection"],
        initial_evidence=source.initial_evidence,
        initial_checks_ref=source.saved["map_initial_checks_ref"],
        terminal_return_ref=returned,
        capture_intent_ref=final.intent_ref,
        capture_result_ref=final.result_ref,
        trace_ref=trace_ref,
        trace_snapshot_ref=EvidenceRef.model_validate(actor["trace_snapshot_ref"]),
    )
    ref = n.put(selected)
    source.saved["map_terminal_ref"] = ref
    # Full original trace/initial/capture validation; never another observation,
    # model request, native process capture or MapData reference dispatch.
    read_map_navigation_terminal(source.c.evidence, n.records, ref, op, control)
    source.saved["map_request_selection"] = dict(
        not_applicable="navigation_page_identity", eligible=[], skipped=[]
    )
