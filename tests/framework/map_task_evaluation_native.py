"""Actual Map capture selection, unified original evaluator and independent re-read."""

from datetime import datetime, timezone
from typing import Any
from lab_generate_skill.bootstrap.map_overlay_evaluation import map_overlay_evaluator
from lab_generate_skill.bootstrap.map_navigation_evaluation import (
    map_navigation_evaluator,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.map.evidence_schema import (
    MapOverlayEvidence,
    MapNavigationEvidence,
)
from lab_generate_skill.evaluators.map.native_overlay import REQUIREMENTS
from lab_generate_skill.evaluators.map.navigation import (
    REQUIREMENTS as NAVIGATION_REQUIREMENTS,
)
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_qualified_source_native import MapQualifiedSource
from map_site_capture_native import inspection, capture, MapCaptureAuthority
from test_slurm_commands import guard
from map_preparation_native import MapPreparation


def judge(source: MapQualifiedSource, actor: dict[str, Any]) -> dict[str, Any]:
    n, c = source.native, source.c
    assert isinstance(n, MapPreparation)
    codec = MapTaskStateCodec(n.public.identity)
    closed_ref = source.saved["browser_closure_ref"]
    closed = ClosureReceipt.model_validate_json(
        c.evidence.read(closed_ref, control=guard(10))
    )
    if closed.status != "closed" or closed.token != source.browser_token:
        raise ValueError("Original Map browser must be closed before full final guard")
    final = capture(
        source,
        SiteCaptureRequest(
            inspection=inspection(
                source, "selected-map-final-guard", parent=closed.operation_id
            ),
            collector_id=codec.collector,
            collector_version="1",
        ),
        MapCaptureAuthority(source),
    )
    chosen: MapOverlayEvidence | MapNavigationEvidence
    if isinstance(n.overlay_spec, NavigationSpec):
        chosen = MapNavigationEvidence(
            environment_ref=source.saved["environment_selection_ref"],
            terminal_ref=source.saved.get("map_terminal_ref"),
            final_guard=final,
            browser_closure_ref=closed_ref,
        )
    else:
        chosen = MapOverlayEvidence(
            environment_ref=source.saved["environment_selection_ref"],
            terminal_ref=source.saved.get("map_terminal_ref"),
            page=source.saved.get("map_page"),
            references=source.saved.get("map_references"),
            final_guard=final,
            browser_closure_ref=closed_ref,
            trace_ref=(
                EvidenceRef.model_validate(actor["trace_ref"])
                if actor.get("trace_ref") is not None
                else None
            ),
            trace_snapshot_ref=(
                EvidenceRef.model_validate(actor["trace_snapshot_ref"])
                if actor.get("trace_snapshot_ref") is not None
                else None
            ),
        )
    contract = EvaluationContract(
        identity=n.public.identity,
        attempt_id=n.attempt_id,
        task_contract_ref=n.binding_ref,
        public_task_ref=n.binding.public_task_ref,
        completion_spec_ref=n.binding.private_spec_ref,
        requirements=(
            NAVIGATION_REQUIREMENTS
            if isinstance(chosen, MapNavigationEvidence)
            else REQUIREMENTS
        ),
        scope="engineering",
    )
    evidence_ref, contract_ref = n.put(chosen), n.put(contract)
    results = []
    assert n.request is not None
    for label in ("judgment", "independent-readonly-review"):
        op = n.request.operation.cleanup(
            "map-" + label, now=datetime.now(timezone.utc), seconds=600
        )
        evaluator = (
            map_navigation_evaluator(chosen, n.records, c.spec, source.site.site, op)
            if isinstance(chosen, MapNavigationEvidence)
            else map_overlay_evaluator(chosen, n.records, c.spec, source.site.site, op)
        )
        value = evaluator.evaluate(contract, c.evidence, c.controls.bind(op))
        results.append(value)
    assert results[0] == results[1]
    return dict(
        evaluation=results[0].model_dump(mode="json"),
        evaluation_ref=n.put(results[0]).model_dump(mode="json"),
        contract_ref=contract_ref.model_dump(mode="json"),
        selected_evidence_ref=evidence_ref.model_dump(mode="json"),
        independent_readonly_equal=True,
        original_request_selection=source.saved.get("map_request_selection"),
        engineering_only=True,
        formal_source_admission=False,
    )
