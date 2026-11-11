"""Actual unified task result/finalizer facts for original closed Map review."""

import os
from typing import Any
from lab_generate_skill.domain.construction import ConstructionAttemptResult
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.bootstrap.map_task_execution import MapTaskExecution
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.bootstrap.execution_task import RecordedExecutionTask
from map_task_preparation_port_fixtures import MapPreparationPortCase
from map_task_execution_initialization_fixtures import CurrentMapHandles
from map_task_execution_current_fixtures import CurrentMapExecutionCase
from preparation_record_fixtures import put
from retrieval_fixtures import reference


def current_map_review_facts(
    case: CurrentMapExecutionCase, result: ConstructionAttemptResult
) -> dict[str, Any]:
    return map_task_review_facts(case.p, case.bundle, case.handles, result)


def map_task_review_facts(
    p: MapPreparationPortCase,
    bundle: (
        MapTaskExecution[RecordedConstructionTask]
        | MapTaskExecution[RecordedExecutionTask]
    ),
    h: CurrentMapHandles,
    result: ConstructionAttemptResult | ExecutionTaskResult,
) -> dict[str, Any]:
    c, store = p.original, p.original.resource.evidence
    initial, capture, final = (
        bundle.initialization.original().state,
        bundle.capture.state,
        bundle.finalization.state,
    )
    assert initial.result is not None and initial.baseline_inputs is not None
    assert initial.baseline_ref is not None and capture.selection_ref is not None
    assert (
        final.reset_ref is not None
        and final.reset_inputs is not None
        and final.reset_selection_ref is not None
    )
    assert final.reset is not None and final.reset.status == "safe"
    assert (
        h.browser is not None
        and h.browser.closed is not None
        and h.browser.phase == "closed"
    )
    assert final.closed is not None and final.closed.closure_refs == (
        capture.closure_ref,
    )
    assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
    return dict(
        engineering_only=True,
        synthetic_kernel=True,
        original_process=os.getpid(),
        configuration=c.resource.spec.model_dump(mode="json"),
        started=p.site.site.model_dump(mode="json"),
        evidence_root=str(c.workspace / "evidence"),
        prepared_browser=dict(
            browser_spec=h.browser.spec.model_dump(mode="json"),
            browser_record=h.browser.closed.model_dump(mode="json"),
            baseline_inputs_ref=reference(
                initial.baseline_inputs, "baseline-inputs/1", store=store
            ).model_dump(mode="json"),
            initial_observation_ref=initial.baseline_inputs.observation_ref.model_dump(
                mode="json"
            ),
        ),
        qualified_source=dict(
            baseline_ref=initial.baseline_ref.model_dump(mode="json"),
            reset_inputs_ref=reference(
                final.reset_inputs, "reset-inputs/1", store=store
            ).model_dump(mode="json"),
            reset_ref=final.reset_ref.model_dump(mode="json"),
            reset_selection_ref=final.reset_selection_ref.model_dump(mode="json"),
            reset_status=final.reset.status,
        ),
        judgment=dict(
            selected_evidence_ref=capture.selection_ref.model_dump(mode="json"),
            contract_ref=put(store, p.plan.evaluation).model_dump(mode="json"),
            evaluation_ref=result.evaluation_ref.model_dump(mode="json"),
        ),
        expected_status=result.evaluation.status,
    )
