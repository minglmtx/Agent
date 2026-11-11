"""Original owned trace consumers; synthetic source/kernel/model transport only."""

from collections import Counter
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.ledger.task_trace_inputs import TaskTraceEventInputs
from lab_generate_skill.application.browser_action import BrowserDispatchFailure
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.adapters.plans.trace_evidence import TraceEvidenceReader
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.trace_events import InteractionObserved
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize(
    "fault", ["none", "stop", "revoked", "cancel", "missing", "foreign", "save"]
)
def test_original_seal_reuses_event_facts_and_restores_without_resending(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, owner):
        current = fixed_task_source_inputs(c, owner, monkeypatch)
        store = c.p.original.resource.evidence
        read, put = store.read, store.put
        validate, append = TraceEvidenceReader.validate, FileTraceJournal.append
        active = False
        checked = []
        inputs = []
        physical: Counter[Any] = Counter()
        forbidden: set[EvidenceRef] = set()
        stop = OperationStopped("DEADLINE_EXCEEDED", c.p.plan.operation.operation_id)

        def retained_read(ref: Any, control: Any = None) -> bytes:
            if active and ref in forbidden:
                physical[ref] += 1
                pytest.fail("Seal re-read an already verified original event payload")
            return read(ref, control=control)

        def retained_put(
            raw: bytes, metadata: Any, control: Any = None, **kw: Any
        ) -> Any:
            if (
                fault == "save"
                and metadata.content_schema == "trace-journal-event/1"
                and json.loads(raw).get("kind") == "sealed"
            ):
                raise OSError("Original seal publication unavailable")
            return put(raw, metadata, control=control, **kw)

        def committed(self: Any, event: Any, *args: Any, **kw: Any) -> Any:
            after = append(self, event, *args, **kw)
            if fault == "stop" and isinstance(event, InteractionObserved):
                raise stop  # Known committed return, not an unknown external effect.
            return after

        def seal(self: Any, trace: Any, op: Any, control: Any) -> None:
            nonlocal active
            held = owner.inputs
            assert held is not None and held.trace_inputs is not None
            carrier = held.trace_inputs
            assert isinstance(carrier, TaskTraceEventInputs)
            inputs.append(carrier)
            history = set(evidence_references(tuple(trace.turns)))
            forbidden.update(
                ref
                for ref in history
                if ref.content_schema
                in {
                    "actor-model-response/1",
                    "model-parameters/1",
                    "actor-model-input/1",
                    "context-preparation/2",
                    "context-preparation-receipt/1",
                    "observation/1",
                }
            )
            responses = [
                ref for ref in history if ref.content_schema == "actor-model-response/1"
            ]
            assert responses and all(ref in carrier.retained_refs for ref in responses)
            before = current.current_calls
            if fault == "revoked":
                current.denied = True
            elif fault == "cancel":
                raise OperationStopped("CANCELLED", op.operation_id)
            elif fault == "missing":
                carrier._verified.remove(responses[0])
            elif fault == "foreign":
                trace = trace.model_copy(
                    update={"max_interactions": trace.max_interactions + 1}
                )
            active = True
            try:
                validate(self, trace, op, control)
            finally:
                active = False
                checked.append((trace, before, current.current_calls))

        monkeypatch.setattr(store, "read", retained_read)
        monkeypatch.setattr(store, "put", retained_put)
        monkeypatch.setattr(FileTraceJournal, "append", committed)
        monkeypatch.setattr(TraceEvidenceReader, "validate", seal)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert all(after > before for _, before, after in checked)
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            if fault == "stop":
                loop = caught.value.primary
                assert isinstance(loop, ActorLoopFailure)
                assert isinstance(loop.primary, BrowserDispatchFailure)
                assert loop.primary.primary is stop
                assert not loop.cleanup_errors
                assert (
                    loop.snapshot is not None
                    and loop.snapshot.project().sealed is not None
                )
            elif fault in ("missing", "foreign"):
                loop = caught.value.primary
                assert isinstance(loop, ActorLoopFailure)
                assert isinstance(loop.primary, OwnershipConflict)
        assert c.native.loader.session.calls == 1 and len(c.handles.completed) == 1
        assert forbidden and not physical
        assert inputs and all(not value.retained_refs for value in inputs)
        assert owner.inputs is not None and not owner.inputs.active
        assert owner.inputs.trace_inputs is None
        assert owner.inputs.trace_input_statistics["verified_event_groups"] > 0
        if fault in ("none", "stop"):
            counts = owner.inputs.trace_input_statistics
            assert counts["seal_body_reads"] == 0 and counts["seal_verified_reuses"] > 0
            assert counts["observation_reuses"] > 0
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
            browser = owner.browser()
            assert browser is not None and browser.phase == "closed"


def test_closed_original_trace_inputs_do_not_restore_history(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, owner):
        fixed_task_source_inputs(c, owner, monkeypatch)
        validate = TraceEvidenceReader.validate
        retained = []

        def seal(self: Any, trace: Any, op: Any, control: Any) -> None:
            held = owner.inputs
            assert held is not None
            carrier = held.trace_inputs
            assert isinstance(carrier, TaskTraceEventInputs)
            carrier.clear()
            retained.append(carrier)
            with pytest.raises(OwnershipConflict, match="lifetime closed"):
                validate(self, trace, op, control)
            raise OwnershipConflict("Original trace lifetime already closed")

        monkeypatch.setattr(TraceEvidenceReader, "validate", seal)
        with pytest.raises(TaskExecutionUnconfirmed):
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert retained and c.native.loader.session.calls == 1
        assert all(not value.retained_refs for value in retained)
