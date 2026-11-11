"""Actual journal/native worker/send review and closed source verification.

The native tokenizer and browser transports are explicit software fixtures;
these tests grant no site, model hardware, old claim or training qualification.
"""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.plans.recorded_observation_sources import (
    RecordedActorObservationSources,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.trace_events import (
    GenerationPlanned,
    ReadObserved,
    ReadPlanned,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from adaptive_actor_loop_fixtures import adaptive_loop_case
from source_review_records import ReadOnlyEvidence
from test_run_journal import command


def test_actual_read_enters_next_input_without_browser_step_and_closed_review_does_not_recount(
    tmp_path: Path,
) -> None:
    c = adaptive_loop_case(tmp_path)
    result = c.runner.run(c.request)
    trace = result.project().sealed
    assert trace is not None and trace.stop_reason == "finished"
    assert trace.generations == 2 and trace.interactions == 1 and c.session.calls == 2
    assert len([e for e in result.events if isinstance(e, ReadPlanned)]) == 1
    assert len([e for e in result.events if isinstance(e, ReadObserved)]) == 1
    read = trace.turns[0].reading
    assert read is not None and read.outcome == "returned" and read.result is not None
    assert trace.turns[0].interaction is None and trace.turns[1].interaction is not None
    first, second = c.session.prompts
    a, b = first.observation_view, second.observation_view
    assert a is not None and b is not None
    assert a.read_result_ref is None and b.read_result_ref == read.result.result_ref
    assert a.reads_used == 0 and b.reads_used == 1
    assert "Value-3" in b.body(second.messages[-1].content)
    assert b.source_spans == read.result.displayed_spans
    assert b.progress_fingerprint == read.result.progress_fingerprint
    store = c.base.base.loop.store
    planned = [e for e in result.events if isinstance(e, GenerationPlanned)]
    receipts = []
    for event in planned:
        assert event.intent.context_preparation_ref is not None
        receipts.append(
            ContextPreparationReceipt.model_validate_json(
                store.read(event.intent.context_preparation_ref)
            )
        )
    assert [tuple(d.kind for d in r.drafts) for r in receipts] == [
        ("compact_full_ax", "local_ax"),
        ("local_ax",),
    ]
    assert [len(r.counts) for r in receipts] == [2, 1]
    client = c.base.base.client
    guard, sources = client.owner_guard, client.installed_sources
    assert guard is not None and sources is not None
    controls = c.base.base.loop.journal.controls
    client.close(
        controls.bind(command("close-adaptive-loop-worker", attempt="attempt"))
    )
    sent = len(c.base.base.channel.sent)
    readonly = ReadOnlyEvidence(tmp_path / "evidence")
    counts = ActorContextCountReviewer(
        readonly,
        c.configuration.profiles[0],
        c.base.model_binding,
        c.base.params,
        client.artifact,
        client.config,
        session_id=client.session_id,
        guard=guard,
        installed_sources=sources,
    )
    closed = RecordedActorObservationSources(c.configuration)
    project, protect = build_actor_context(
        c.configuration.policy, indices=closed.index_for_public
    )
    reviewer = RecordedActorContextInputs(
        readonly,
        EvidenceObservations(readonly, controls),
        project,
        protect,
        counts,
        observation_sources=closed,
    )
    op = command(
        "closed-adaptive-input-review",
        attempt="attempt",
        cleanup_parent="original-adaptive-loop",
    )
    for i, recorded_event in enumerate(result.events):
        if not isinstance(recorded_event, GenerationPlanned):
            continue
        prefix = TraceSnapshot(
            plan=result.plan,
            creation_operation=result.creation_operation,
            events=result.events[:i],
        )
        actual = reviewer.verify(
            c.request, prefix, recorded_event.intent, op, control=controls.bind(op)
        )
        assert actual in c.session.prompts
    assert len(c.base.base.channel.sent) == sent and c.session.closed == 1
    with pytest.raises(ActorLoopFailure):
        c.runner.run(c.request)
    assert c.session.calls == 2


def test_small_complete_page_stops_after_one_count_and_has_no_read_events(
    tmp_path: Path,
) -> None:
    c = adaptive_loop_case(tmp_path, mode="small")
    result = c.runner.run(c.request)
    trace = result.project().sealed
    assert trace is not None and trace.generations == trace.interactions == 1
    event = next(e for e in result.events if isinstance(e, GenerationPlanned))
    assert event.intent.context_preparation_ref is not None
    receipt = ContextPreparationReceipt.model_validate_json(
        c.base.base.loop.store.read(event.intent.context_preparation_ref)
    )
    assert (
        tuple(d.kind for d in receipt.drafts) == ("compact_full_ax",)
        and len(receipt.counts) == 1
    )
    assert not any(isinstance(e, (ReadPlanned, ReadObserved)) for e in result.events)
    assert c.session.prompts[0].observation_view is not None
    assert c.session.prompts[0].observation_view.mode == "compact_full"


def test_current_directory_duplicate_stops_on_two_no_progress_reads_without_forced_action(
    tmp_path: Path,
) -> None:
    c = adaptive_loop_case(tmp_path, mode="duplicate")
    result = c.runner.run(c.request)
    trace = result.project().sealed
    assert trace is not None and trace.stop_reason == "error"
    assert trace.generations == 2 and trace.interactions == 0
    assert c.session.calls == 2 and all(t.reading is not None for t in trace.turns)
    assert len([e for e in result.events if isinstance(e, ReadObserved)]) == 2
