"""Real owned result-journal consumer; synthetic kernel/source/model premises."""

from collections import Counter
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.trace_journal_evidence import (
    TraceJournalEvidence,
)
from lab_generate_skill.application.actor_context_review_inputs import (
    ActorContextReviewInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.trace_events import GenerationObserved
from lab_generate_skill.domain.errors import OperationStopped
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize("fault", ["none", "revoked", "cancel", "response", "save"])
def test_original_result_commit_uses_prepared_bodies_and_current_authority(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, resources):
        current = fixed_task_source_inputs(c, resources, monkeypatch)
        store = c.p.original.resource.evidence
        original_read, original_put = store.read, store.put
        original_event = TraceJournalEvidence.event
        reading = False
        response = None
        physical: Counter[Any] = Counter()
        carried = []
        current_counts = []
        observed = []

        def read(reference: Any, control: Any = None) -> bytes:
            if reading:
                physical[reference] += 1
                if fault == "response" and reference == response:
                    return b"corrupt-new-response"
            return original_read(reference, control=control)

        def put(raw: bytes, metadata: Any, control: Any = None, **kwargs: Any) -> Any:
            if (
                fault == "save"
                and metadata.content_schema == "trace-journal-event/1"
                and json.loads(raw).get("kind") == "generation_observed"
            ):
                raise OSError("Original result snapshot publication unavailable")
            return original_put(raw, metadata, control=control, **kwargs)

        def event(
            self: Any,
            before: Any,
            after: Any,
            value: Any,
            op: Any,
            control: Any,
            **kwargs: Any,
        ) -> None:
            nonlocal reading, response
            if not isinstance(value, GenerationObserved):
                return original_event(self, before, after, value, op, control, **kwargs)
            held = kwargs.get("generation_inputs")
            assert isinstance(held, ActorContextReviewInputs)
            intent = before.project().intent
            assert intent is not None and intent.matches(value.generation)
            selected = [
                intent.input_ref,
                intent.parameters_ref,
                intent.before_observation_ref,
                intent.context_preparation_ref,
            ]
            assert all(ref in held.bodies for ref in selected)
            carried.append((held, selected))
            observed.append(value)
            response = value.generation.response_ref
            assert response is not None and response not in held.bodies
            previous = current.current_calls
            if fault == "revoked":
                current.denied = True
            if fault == "cancel":
                raise OperationStopped("CANCELLED", op.operation_id)
            reading = True
            try:
                original_event(self, before, after, value, op, control, **kwargs)
            finally:
                reading = False
                current_counts.append((previous, current.current_calls))

        monkeypatch.setattr(store, "read", read)
        monkeypatch.setattr(store, "put", put)
        monkeypatch.setattr(TraceJournalEvidence, "event", event)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert all(physical[ref] == 0 for ref in carried[0][1])
            assert physical[response] == 1
            assert all(after > before for before, after in current_counts)
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failure:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert failure.value.primary is not None
        assert len(observed) == 1 and c.native.loader.session.calls == 1
        assert carried and all(not held.bodies for held, _ in carried)
        assert resources.inputs is not None and not resources.inputs.active


@pytest.mark.parametrize("value", [None, object(), "not-a-provider"])
def test_result_handoff_rejects_missing_or_wrong_provider(
    tmp_path: Path, value: Any
) -> None:
    from trace_journal_fixtures import fixture

    data = fixture(tmp_path)
    journal = data.journal()
    with pytest.raises(TypeError):
        journal.with_generation_inputs(value)
