"""Original owned commit consumer and measured viewport bodies; synthetic live edges."""

from collections import Counter
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.plans.trace_journal_evidence import (
    TraceJournalEvidence,
)
from lab_generate_skill.adapters.plans.observations import ObservationReader
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.application.actor_context_review_inputs import (
    ActorContextReviewInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import ObservationArtifact
from lab_generate_skill.domain.observation_viewport import (
    VIEWPORT_METADATA,
    VIEWPORT_NAME,
)
from lab_generate_skill.domain.trace_events import GenerationPlanned
from evidence_control_fixtures import EvidenceFixtureStore
from retrieval_fixtures import reference
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs
from test_public_viewport_handoff import index_for
from test_slurm_commands import guard


@pytest.mark.parametrize("fault", ["none", "revoked", "cancel", "body", "foreign"])
def test_original_generation_intent_uses_one_bound_reader_for_plan_and_event_with_fresh_gates(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, resources):
        current = fixed_task_source_inputs(c, resources, monkeypatch)
        store = c.p.original.resource.evidence
        read0 = store.read
        plan0, event0 = TraceJournalEvidence.plan, TraceJournalEvidence.event
        provider0 = RecordedActorContextInputs.generation_inputs
        active = False
        committing_intent = False
        append0 = FileTraceJournal.append
        carriers: list[ActorContextReviewInputs] = []
        provider_inputs: list[ActorContextReviewInputs] = []
        plan_calls: list[tuple[int, int]] = []
        event_readers = []
        physical: Counter[EvidenceRef] = Counter()

        def read(ref: Any, control: Any = None) -> bytes:
            if active:
                physical[ref] += 1
                if fault == "body" and ref.content_schema == "run-plan/3":
                    return b"corrupt-original-plan-body"
            return read0(ref, control=control)

        def append(self: Any, value: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal committing_intent
            previous = committing_intent
            committing_intent = isinstance(value, GenerationPlanned)
            try:
                return append0(self, value, *args, **kwargs)
            finally:
                committing_intent = previous

        def provider(self: Any, intent: Any, control: Any) -> Any:
            assert self._inputs is not None
            provider_inputs.append(self._inputs)
            if fault == "foreign" and committing_intent:
                intent = intent.model_copy(
                    update={
                        "scope": intent.scope.model_copy(
                            update={"context_id": "foreign-context"}
                        )
                    }
                )
            return provider0(self, intent, control)

        def plan(
            self: Any,
            value: Any,
            op: Any,
            control: Any,
            *,
            generation_inputs: Any = None,
        ) -> None:
            nonlocal active
            if generation_inputs is None:
                return plan0(self, value, op, control)
            held = generation_inputs
            assert isinstance(held, ActorContextReviewInputs) and held.bodies
            carriers.append(held)
            before = current.current_calls
            if fault == "revoked":
                current.denied = True
            elif fault == "cancel":
                raise OperationStopped("CANCELLED", op.operation_id)
            if fault == "body":
                assert value.binding.run.plan_ref not in held.bodies
            active = True
            try:
                plan0(self, value, op, control, generation_inputs=held)
            finally:
                active = False
                plan_calls.append((before, current.current_calls))
            expected = (
                value.binding.run.plan_ref,
                value.binding.run.release_ref,
                value.binding.claim_ref,
                value.initial_observation_ref,
            )
            assert all(ref in held.bodies for ref in expected)

        def event(
            self: Any,
            before: Any,
            after: Any,
            value: Any,
            op: Any,
            control: Any,
            **kwargs: Any,
        ) -> None:
            if isinstance(value, GenerationPlanned):
                held = kwargs.get("generation_inputs")
                assert carriers and held is carriers[-1]
                event_readers.append(held)
            return event0(self, before, after, value, op, control, **kwargs)

        monkeypatch.setattr(store, "read", read)
        monkeypatch.setattr(FileTraceJournal, "append", append)
        monkeypatch.setattr(RecordedActorContextInputs, "generation_inputs", provider)
        monkeypatch.setattr(TraceJournalEvidence, "plan", plan)
        monkeypatch.setattr(TraceJournalEvidence, "event", event)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert (
                result.evaluation.status == "success"
                and c.native.loader.session.calls == 1
            )
            assert carriers and event_readers == carriers
            assert all(after > before for before, after in plan_calls)
            assert resources.inputs and resources.inputs.finalization is None
            assert (
                c.bundle.finalization.state.reset
                and c.bundle.finalization.state.reset.status == "safe"
            )
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert (
                failed.value.primary
                and c.native.loader.session.calls == 0
                and not event_readers
            )
            loop = failed.value.primary
            dispatch = getattr(loop, "primary", None)
            assert (
                dispatch is not None
                and getattr(dispatch, "phase", None) == "commit_intent"
            )
            primary = getattr(dispatch, "primary", None)
            expected_error = (
                EvidenceIntegrityError
                if fault == "body"
                else OperationStopped if fault == "cancel" else OwnershipConflict
            )
            assert isinstance(primary, expected_error)
            if fault == "revoked":
                assert any(after > before for before, after in plan_calls)
        assert provider_inputs and all(not item.bodies for item in provider_inputs)
        assert resources.inputs is not None and not resources.inputs.active


def test_same_generation_viewport_read_once_and_new_generation_rechecks(
    tmp_path: Path,
) -> None:
    _, observed, viewport = index_for()
    store = EvidenceFixtureStore(tmp_path)
    assert (
        store.put(viewport.model_dump_json().encode(), VIEWPORT_METADATA)
        == viewport.reference
    )
    observed_ref = reference(observed, "observation/1", "public", store)
    calls: Counter[EvidenceRef] = Counter()

    class Reader:
        def read(self, ref: EvidenceRef, control: Any) -> bytes:
            control.checkpoint()
            calls[ref] += 1
            return store.read(ref, control=control)

    raw = Reader()
    control = guard(30)
    first = ActorContextReviewInputs(raw)
    reader = ObservationReader(first)
    a = reader.load(observed_ref, control)
    b = reader.load(observed_ref, control)
    assert a == b and calls[observed_ref] == calls[viewport.reference] == 1
    first.clear()
    with pytest.raises(OwnershipConflict, match="closed"):
        reader.load(observed_ref, control)
    second = ActorContextReviewInputs(raw)
    assert ObservationReader(second).load(observed_ref, control) == a
    assert calls[observed_ref] == calls[viewport.reference] == 2
    second.clear()


def test_retained_viewport_bytes_still_require_same_capture_binding(
    tmp_path: Path,
) -> None:
    _, before, viewport0 = index_for("before-scroll")
    _, after, viewport1 = index_for("after-scroll")
    store = EvidenceFixtureStore(tmp_path)
    for viewport in (viewport0, viewport1):
        assert (
            store.put(viewport.model_dump_json().encode(), VIEWPORT_METADATA)
            == viewport.reference
        )
    first = reference(after, "observation/1", "public", store)
    wrong = before.model_copy(
        update={
            "artifacts": (
                ObservationArtifact(name=VIEWPORT_NAME, reference=viewport1.reference),
            )
        }
    )
    wrong_ref = reference(wrong, "observation/1", "public", store)
    inputs = ActorContextReviewInputs(store)
    reader = ObservationReader(inputs)
    control = guard(30)
    reader.load(first, control)
    with pytest.raises(EvidenceIntegrityError):
        reader.load(wrong_ref, control)
    inputs.clear()
