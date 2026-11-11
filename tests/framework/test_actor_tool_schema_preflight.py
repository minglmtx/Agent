"""Invalid reads are checked before intent and consume neither quota nor actions."""

import json
from pathlib import Path
from typing import Any
import pytest

from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.application.actor_rejection_progress import (
    ActorInvalidProposalsStopped,
)
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalError,
    ActorProposalFeedback,
)
from lab_generate_skill.domain.actor_response import ActorParseFailure
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.observation_read import (
    ReadObservationRegions,
    ObservationRegionRange,
    ListObservationRegions,
)
from lab_generate_skill.domain.trace_events import (
    ReadPlanned,
    DecisionRejected,
    ActionPlanned,
    GenerationObserved,
)
from adaptive_actor_loop_fixtures import adaptive_loop_case
from observation_read_fixtures import indexed
from state_contract_fixtures import op
from test_snapshot_observation_reads import reader_case

NEW_POLICY = {
    "schema_version": "observation-read-policy/2",
    "max_consecutive_invalid_proposals": 3,
    "max_identical_invalid_proposals": 2,
    "warn_remaining": 3,
}


@pytest.mark.parametrize("kind", ["unknown", "wrong_rows", "beyond_characters"])
def test_retained_index_preflight_rejects_only_input_errors_without_read_count_or_publication(
    tmp_path: Path, kind: str
) -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n\t[3] button B\n")
    reads, progress, case, _, session = reader_case(tmp_path, index)
    ranges = {
        "unknown": ObservationRegionRange(region_id="heading-111", unit="whole_region"),
        "wrong_rows": ObservationRegionRange(
            region_id="ax-line-1", unit="data_rows", start=0, end=1
        ),
        "beyond_characters": ObservationRegionRange(
            region_id="ax-line-1", unit="codepoints", start=0, end=999
        ),
    }
    request = ReadObservationRegions(
        request_id="invalid-proposal",
        snapshot=index.snapshot,
        output_tokens=100,
        ranges=(ranges[kind],),
    )
    with pytest.raises(ActorProposalError) as caught:
        reads.check_proposal(request, progress=progress, control=case.control)
    assert caught.value.feedback.code == (
        "UNKNOWN_REGION" if kind == "unknown" else "RANGE_OUT_OF_BOUNDS"
    )
    assert (
        progress.reads_used == 0
        and not reads._spent
        and not session.body_calls
        and session.calls == 0
    )
    reads.close()
    case.client.close(case.control)


def test_issued_cursor_binding_is_checked_without_dispatch_and_lost_mapping_is_engineering(
    tmp_path: Path,
) -> None:
    index = indexed(
        "[1] RootWebArea\n\t[2] button A\n\t[3] button B\n", directory_entries=1
    )
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ListObservationRegions(
        request_id="directory",
        snapshot=index.snapshot,
        output_tokens=index.policy.body_max_tokens,
    )
    page = reads.automatic_directory(request, op("automatic"), control=case.control)
    assert page.payload.continuation
    continuation = request.model_copy(
        update={"request_id": "continue", "continuation": page.payload.continuation}
    )
    reads.check_proposal(continuation, progress=progress, control=case.control)
    for altered in (
        continuation.model_copy(update={"output_tokens": 7999}),
        continuation.model_copy(update={"continuation": "read-forged"}),
    ):
        with pytest.raises(ActorProposalError) as caught:
            reads.check_proposal(altered, progress=progress, control=case.control)
        assert caught.value.feedback.code == "INVALID_CONTINUATION"
    reads._cursors.clear()
    with pytest.raises(OwnershipConflict, match="mapping"):
        reads.check_proposal(continuation, progress=progress, control=case.control)
    assert not reads._spent and not session.body_calls
    reads.close()
    case.client.close(case.control)


@pytest.mark.parametrize("mode,expected", [("identical", 2), ("distinct", 3)])
def test_actual_loop_records_rejections_then_stops_before_another_generation_without_borrowing_read_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: int
) -> None:
    c = adaptive_loop_case(
        tmp_path,
        read_policy_changes={
            "schema_version": "observation-read-policy/2",
            "max_consecutive_invalid_proposals": 3,
            "max_identical_invalid_proposals": 2,
            "consecutive_no_progress": 1,
            "warn_remaining": 3,
        },
    )

    def infer(
        tokens: tuple[int, ...], parameters: Any, control: Any
    ) -> LocalActorOutput:
        prompt = c.session.last_prompt
        assert prompt and prompt.observation_view
        c.session.prompts.append(prompt)
        c.session.calls += 1
        value: dict[str, Any]
        if mode == "identical":
            value = {
                "thought": str(c.session.calls),
                "read": {
                    "tool": "read_region",
                    "snapshot_sha256": prompt.observation_view.snapshot.observation_ref.sha256,
                    "output_tokens": 8,
                    "ranges": [
                        {"region_id": f"ax-line-{n}", "unit": "whole_region"}
                        for n in range(5)
                    ],
                },
            }
        else:
            value = (
                {"action": "click()"},
                {"read": {"tool": "unknown"}},
                {"action": "fill('x',42)"},
            )[c.session.calls - 1]
        return LocalActorOutput(
            text=json.dumps(value),
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(c.session, "infer", infer)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    failure = caught.value
    assert isinstance(failure.primary, ActorInvalidProposalsStopped)
    assert (
        failure.primary.count == failure.primary.limit == expected
        and c.session.calls == expected
    )
    assert failure.cleanup_errors == () and failure.snapshot
    trace = failure.snapshot.project().sealed
    assert (
        trace
        and trace.stop_reason == "error"
        and trace.generations == expected
        and trace.interactions == 0
    )
    assert (
        sum(isinstance(event, DecisionRejected) for event in failure.snapshot.events)
        == expected
    )
    assert not any(
        isinstance(event, (ReadPlanned, ActionPlanned))
        for event in failure.snapshot.events
    )
    store = c.base.base.loop.store
    for n, turn in enumerate(trace.turns, 1):
        assert turn.decision and turn.decision.failure_ref
        fact = ActorParseFailure.model_validate_json(
            store.read(turn.decision.failure_ref)
        )
        feedback = ActorProposalFeedback.model_validate_json(fact.message)
        assert feedback.consecutive_invalid == n and not feedback.executed
    for prompt in c.session.prompts:
        assert (
            prompt.observation_view
            and prompt.observation_view.reads_used
            == prompt.observation_view.no_progress
            == 0
        )


def test_valid_new_read_uses_original_count_probe_and_the_next_input_has_real_reset_progress(
    tmp_path: Path,
) -> None:
    c = adaptive_loop_case(tmp_path, read_policy_changes=NEW_POLICY)
    result = c.runner.run(c.request)
    trace = result.project().sealed
    assert trace and trace.stop_reason == "finished" and c.session.calls == 2
    assert sum(isinstance(event, ReadPlanned) for event in result.events) == 1
    assert "browsergym-adaptive-count-probe-v2" in c.session.complete_inputs
    view = c.session.prompts[-1].observation_view
    assert view and view.reads_used == 1 and view.invalid_proposals
    assert (
        view.invalid_proposals.consecutive_invalid
        == view.invalid_proposals.repeated_invalid
        == 0
    )


@pytest.mark.parametrize("kind", ["internal", "permission", "cancel", "storage"])
def test_preflight_engineering_failures_preserve_return_and_never_become_model_corrections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    c = adaptive_loop_case(tmp_path, read_policy_changes=NEW_POLICY)
    error = {
        "internal": ValueError("internal retained-index contradiction"),
        "permission": OwnershipConflict("revoked"),
        "cancel": OperationStopped("CANCELLED", "preflight"),
        "storage": OSError("storage unavailable"),
    }[kind]

    def check(*args: Any, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(c.sources, "check_proposal", check)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert (
        caught.value.primary is error and c.session.calls == 1 and caught.value.snapshot
    )
    assert not any(
        isinstance(event, (DecisionRejected, ReadPlanned, ActionPlanned))
        for event in caught.value.snapshot.events
    )
    assert (
        sum(
            isinstance(event, GenerationObserved)
            for event in caught.value.snapshot.events
        )
        == 1
    )
