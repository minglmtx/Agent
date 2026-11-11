"""Adopt actual new port facts into the unchanged original restore/read-only tail."""

from typing import Any
import os
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from map_task_operations_native import execute
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from task_capture_port_fixtures import CapturePortCase


def restore_facts(case: CapturePortCase) -> dict[str, Any]:
    i, capture = case.initial, case.capture
    p, init = i.preparation, i.initialization
    c, source, prep = p.original, p.source, p.preparation.state
    store, state = c.resource.evidence, init.state
    assert (
        capture.state.selection_ref is not None
        and capture.state.closure_ref is not None
    )
    assert (
        state.baseline_inputs is not None
        and state.baseline is not None
        and state.baseline_ref is not None
    )
    assert prep.result is not None and prep.environment is not None
    assert (
        prep.environment_selection_ref is not None and prep.snapshot_result is not None
    )
    assert prep.snapshot_ref is not None
    assert i.browser.phase == "closed" and i.browser.closed is not None
    source.environment, source.publication = prep.environment, prep.result.publication
    source.plan, source.plan_ref = p.reset, p.reset_ref
    source.browser_token = p.reset.attempt_allocations[0]
    source.saved.update(
        environment_selection=EnvironmentSelection.model_validate_json(
            store.read(prep.environment_selection_ref)
        ),
        environment_selection_ref=prep.environment_selection_ref,
        environment_ref=prep.environment_ref,
        snapshot=source.parse_snapshot(prep.snapshot_result),
        snapshot_ref=prep.snapshot_ref,
        baseline_inputs=state.baseline_inputs,
        baseline=state.baseline,
        baseline_ref=state.baseline_ref,
        initial_ref=state.baseline_inputs.initial_ref,
        browser_closed_before_restore=True,
        browser_closure_ref=capture.state.closure_ref,
    )
    evaluated = case.evaluator.evaluate(
        p.plan.evaluation, store, c.resource.controls.bind(p.plan.operation)
    )
    assert evaluated.status in ("success", "failure")
    request, result = execute(source, "restore", prep.snapshot_ref)
    qualified = source.after_restore(request, result)
    return dict(
        engineering_only=True,
        synthetic_kernel=True,
        original_process=os.getpid(),
        configuration=c.resource.spec.model_dump(mode="json"),
        started=p.site.site.model_dump(mode="json"),
        evidence_root=str(c.workspace / "evidence"),
        prepared_browser=dict(
            browser_spec=i.browser.spec.model_dump(mode="json"),
            browser_record=i.browser.closed.model_dump(mode="json"),
            baseline_inputs_ref=reference(
                state.baseline_inputs, "baseline-inputs/1", store=store
            ).model_dump(mode="json"),
            initial_observation_ref=state.baseline_inputs.observation_ref.model_dump(
                mode="json"
            ),
        ),
        qualified_source=qualified,
        judgment=dict(
            selected_evidence_ref=capture.state.selection_ref.model_dump(mode="json"),
            contract_ref=put(store, p.plan.evaluation).model_dump(mode="json"),
            evaluation_ref=put(store, evaluated).model_dump(mode="json"),
        ),
        expected_status=evaluated.status,
    )
