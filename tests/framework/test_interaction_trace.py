"""Pure history invariants: exact identities, independent counts and uncertainty."""

from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.actor_generation import ActorDecision, ActorGeneration
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.interaction import InteractionEvent
from lab_generate_skill.domain.trace import InteractionTrace, TraceTurn
from trace_fixtures import fixture


def test_actual_return_counts_differ_from_model_calls_and_round_trip() -> None:
    trace = fixture().trace
    assert (trace.generations, trace.completed_generations, trace.interactions) == (
        3,
        3,
        2,
    )
    assert trace.final_observation_ref != trace.initial_observation_ref
    assert InteractionTrace.model_validate_json(trace.model_dump_json()) == trace
    assert InteractionTrace.model_validate(trace) == trace
    assert "interactions" not in trace.model_dump()


@pytest.mark.parametrize(
    "outcome,completed",
    [
        ("not_dispatched", 1),
        ("uncertain", 1),
        ("failed", 0),
        ("generation_unknown", 0),
        ("unprocessed", 1),
        ("invalid", 1),
    ],
)
def test_non_returns_never_inflate_interactions(outcome: str, completed: int) -> None:
    trace = fixture(outcomes=(outcome,)).trace
    assert (trace.generations, trace.completed_generations, trace.interactions) == (
        1,
        completed,
        0,
    )
    assert trace.final_observation_ref == trace.initial_observation_ref


@pytest.mark.parametrize(
    "outcome",
    ["failed", "generation_unknown", "unprocessed", "uncertain", "returned_incomplete"],
)
def test_no_new_call_after_interruption_or_uncertainty(outcome: str) -> None:
    with pytest.raises(ValidationError, match="No new generation"):
        fixture(outcomes=(outcome, "returned"))


def test_observation_failure_keeps_confirmed_return_and_unknown_separate() -> None:
    incomplete = fixture(outcomes=("returned_incomplete",)).trace
    assert incomplete.interactions == 1 and incomplete.uncertain_interactions == 0
    assert incomplete.stop_reason == "error"
    assert incomplete.final_observation_ref == incomplete.initial_observation_ref
    unknown = fixture(outcomes=("uncertain",)).trace
    assert unknown.interactions == 0 and unknown.uncertain_interactions == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("turns", None),
        ("turns", []),
        ("max_generations", True),
        ("max_generations", 0),
        ("max_generations", 10001),
        ("max_interactions", 1.0),
        ("max_interactions", -1),
        ("stop_reason", "success"),
        ("schema_version", "interaction-trace/0"),
    ],
)
def test_strict_trace_roots(field: str, value: object) -> None:
    trace = fixture().trace
    with pytest.raises(ValidationError):
        InteractionTrace.model_validate(trace.model_copy(update={field: value}))


def test_empty_interrupted_trace_and_frozen_limits() -> None:
    trace = fixture(outcomes=()).trace
    assert trace.generations == trace.interactions == 0
    for reason in ("finished", "uncertain", "generation_limit", "interaction_limit"):
        with pytest.raises(ValidationError):
            InteractionTrace.model_validate(
                trace.model_copy(update={"stop_reason": reason})
            )
    full = fixture(terminal=False).trace
    for changes in (
        {"max_generations": 3, "stop_reason": "generation_limit"},
        {"max_interactions": 2, "stop_reason": "interaction_limit"},
    ):
        assert (
            InteractionTrace.model_validate(
                full.model_copy(update=changes)
            ).interactions
            == 2
        )
    for invalid_changes in (
        {"max_generations": 2},
        {"max_interactions": 1},
        {"stop_reason": "generation_limit"},
        {"stop_reason": "interaction_limit"},
    ):
        with pytest.raises(ValidationError):
            InteractionTrace.model_validate(full.model_copy(update=invalid_changes))


@pytest.mark.parametrize("field", ["generation_id", "request_id", "operation"])
def test_reused_generation_identity_rejected(field: str) -> None:
    trace = fixture(outcomes=("invalid", "invalid")).trace
    first, last = trace.turns
    changed = last.generation.model_copy(
        update={field: getattr(first.generation, field)}
    )
    decision = cast(ActorDecision, last.decision).model_copy(
        update={"generation_id": changed.generation_id}
    )
    with pytest.raises(ValidationError, match="cannot repeat"):
        InteractionTrace.model_validate(
            trace.model_copy(
                update={
                    "turns": (
                        first,
                        last.model_copy(
                            update={"generation": changed, "decision": decision}
                        ),
                    )
                }
            )
        )


@pytest.mark.parametrize(
    "change",
    ["generation_scope", "before", "decision", "action", "result_action", "operation"],
)
def test_cross_linked_records_rejected(change: str) -> None:
    trace = fixture().trace
    first = trace.turns[0]
    turn = trace.turns[-1]
    event = cast(InteractionEvent, turn.interaction)
    assert event.result is not None and turn.decision is not None
    changes: dict[str, object] = {}
    if change == "generation_scope":
        changes["generation"] = turn.generation.model_copy(
            update={
                "scope": turn.generation.scope.model_copy(
                    update={"context_id": "other"}
                )
            }
        )
    elif change == "before":
        changes["generation"] = turn.generation.model_copy(
            update={"before_observation_ref": trace.initial_observation_ref}
        )
    elif change == "decision":
        changes["decision"] = turn.decision.model_copy(
            update={"generation_id": first.generation.generation_id}
        )
    elif change == "action":
        changes["interaction"] = event.model_copy(
            update={"action": event.action.model_copy(update={"payload": "click('3')"})}
        )
    elif change == "result_action":
        changes["interaction"] = event.model_copy(
            update={"result": event.result.model_copy(update={"action_id": "other"})}
        )
    else:
        gen = turn.generation.model_copy(update={"operation": trace.operation})
        changes["generation"] = gen
    with pytest.raises((OwnershipConflict, ValidationError)):
        InteractionTrace.model_validate(
            trace.model_copy(
                update={"turns": (*trace.turns[:-1], turn.model_copy(update=changes))}
            )
        )


@pytest.mark.parametrize("status", ["failed", "uncertain"])
def test_generation_cannot_invent_response_on_failure(status: str) -> None:
    gen = fixture().trace.turns[0].generation
    with pytest.raises(ValidationError):
        ActorGeneration.model_validate(gen.model_copy(update={"status": status}))


def test_returned_and_nonreturned_results_are_exclusive() -> None:
    turn = fixture().trace.turns[-1]
    event = cast(InteractionEvent, turn.interaction)
    for changes in (
        {"outcome": "uncertain"},
        {"outcome": "not_dispatched"},
        {"result": None},
    ):
        with pytest.raises(ValidationError):
            InteractionEvent.model_validate(event.model_copy(update=changes))
    with pytest.raises(ValidationError):
        TraceTurn.model_validate(turn.model_copy(update={"decision": None}))


@pytest.mark.parametrize("value", ["", "  ", "\ud800", "中" * 21846, None, 123])
def test_action_payload_extremes(value: object) -> None:
    action = BrowserAction(
        action_id="a", protocol_id="p", name="click", payload="click('2')"
    )
    with pytest.raises(ValidationError):
        BrowserAction.model_validate(action.model_copy(update={"payload": value}))


def test_payload_exact_utf8_and_size_boundary() -> None:
    raw = "中" * 21845 + "\n"
    action = BrowserAction(action_id="a", protocol_id="p", name="click", payload=raw)
    assert len(action.payload.encode()) == 65536 and action.payload == raw
    with pytest.raises(ValidationError):
        BrowserAction.model_validate(
            {**action.model_dump(), "handler": "private callback"}
        )


def test_terminal_and_uncertain_cannot_be_relabeled_success_or_error() -> None:
    for outcome in ("returned", "uncertain", "generation_unknown"):
        trace = fixture(outcomes=(outcome,)).trace
        with pytest.raises(ValidationError):
            InteractionTrace.model_validate(
                trace.model_copy(update={"stop_reason": "error"})
            )
