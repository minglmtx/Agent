"""Export new finalizer facts to the unchanged original read-only review."""

import os
from typing import Any
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from task_capture_port_fixtures import CapturePortCase
from task_finalization_port_fixtures import bind_finalization


def finalized_facts(case: CapturePortCase) -> dict[str, Any]:
    i = case.initial
    p, init, capture = i.preparation, i.initialization.state, case.capture.state
    c, store = p.original, p.original.resource.evidence
    evaluated = case.evaluator.evaluate(
        p.plan.evaluation, store, c.resource.controls.bind(p.plan.operation)
    )
    assert evaluated.status in ("success", "failure")
    f = bind_finalization(case)
    closed = f.close()
    reset_ref = f.restore()
    s = f.finalizer.state
    assert s.reset is not None and s.reset.status == "safe"
    assert s.reset_inputs is not None and s.reset_selection_ref is not None
    assert s.reset_ref == reset_ref and s.phase == "restored"
    assert init.baseline_inputs is not None and init.baseline_ref is not None
    assert capture.selection_ref is not None and capture.closure_ref is not None
    assert closed.closure_refs == (capture.closure_ref,)
    assert i.browser.closed is not None and i.browser.phase == "closed"
    assert len(c.resource.channels) == 1 and len(i.backend.resource.channels) == 1
    assert f.resume.calls == 1 and f.unstarted.calls == 0
    assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
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
                init.baseline_inputs, "baseline-inputs/1", store=store
            ).model_dump(mode="json"),
            initial_observation_ref=init.baseline_inputs.observation_ref.model_dump(
                mode="json"
            ),
        ),
        qualified_source=dict(
            baseline_ref=init.baseline_ref.model_dump(mode="json"),
            reset_inputs_ref=reference(
                s.reset_inputs, "reset-inputs/1", store=store
            ).model_dump(mode="json"),
            reset_ref=reset_ref.model_dump(mode="json"),
            reset_selection_ref=s.reset_selection_ref.model_dump(mode="json"),
            reset_status=s.reset.status,
        ),
        judgment=dict(
            selected_evidence_ref=capture.selection_ref.model_dump(mode="json"),
            contract_ref=put(store, p.plan.evaluation).model_dump(mode="json"),
            evaluation_ref=put(store, evaluated).model_dump(mode="json"),
        ),
        expected_status=evaluated.status,
    )
