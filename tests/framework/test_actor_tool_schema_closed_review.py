"""Actual recovery traces and same captured cursor facts; no producer replay."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.actor_closed_review import review_actor
from lab_generate_skill.actor.tool_schema_validation import actor_schema_violations
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalFeedback
from lab_generate_skill.domain.actor_response import ActorParseFailure
from lab_generate_skill.domain.observation_read import ListObservationRegions
from lab_generate_skill.domain.observation_read_progress import observation_request_key
from lab_generate_skill.domain.trace_events import DecisionRejected, ReadPlanned
from lab_generate_skill.policies.actor_tool_schemas import materialize_actor_tools
from lab_generate_skill.policies.observation_display import observation_read_body
from adaptive_actor_loop_fixtures import AdaptiveSession
from adaptive_actor_review_fixtures import closed_adaptive_review
from observation_read_fixtures import indexed
from state_contract_fixtures import op
from test_snapshot_observation_reads import reader_case
from test_actor_tool_schema_preflight import NEW_POLICY


@pytest.mark.parametrize(
    "kind,code",
    [
        ("schema", "RANGE_COUNT_EXCEEDED"),
        ("unknown", "UNKNOWN_REGION"),
        ("range", "RANGE_OUT_OF_BOUNDS"),
        ("branch", "WRONG_TOOL_BRANCH"),
    ],
)
def test_actual_typed_rejection_then_read_then_finish_is_independently_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, code: str
) -> None:
    original = AdaptiveSession.infer

    def infer(
        self: AdaptiveSession, tokens: tuple[int, ...], parameters: Any, control: Any
    ) -> LocalActorOutput:
        if self.calls >= 2:
            return original(self, tokens, parameters, control)
        prompt = self.last_prompt
        assert prompt is not None and prompt.observation_view
        self.calls += 1
        self.prompts.append(prompt)
        reading: dict[str, Any] = dict(
            tool="read_region",
            snapshot_sha256=prompt.observation_view.snapshot.observation_ref.sha256,
            output_tokens=8,
            ranges=[dict(region_id="ax-line-1", unit="data_rows", start=3, end=4)],
        )
        if self.calls == 1:
            if kind == "schema":
                reading["ranges"] = [
                    dict(region_id=f"ax-line-{n}", unit="whole_region")
                    for n in range(5)
                ]
            elif kind == "unknown":
                reading["ranges"] = [
                    dict(region_id="ax-line-19999", unit="whole_region")
                ]
            elif kind == "range":
                reading["ranges"] = [
                    dict(region_id="ax-line-1", unit="data_rows", start=0, end=9999)
                ]
        value: dict[str, Any] = (
            {"action": "read_region"}
            if self.calls == 1 and kind == "branch"
            else {"read": reading}
        )
        return LocalActorOutput(
            text=json.dumps(value),
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(AdaptiveSession, "infer", infer)
    c = closed_adaptive_review(tmp_path, read_policy_changes=NEW_POLICY)
    a = c.actor
    sent, counted = len(a.base.base.channel.sent), len(a.session.body_calls)
    summary = review_actor(
        a.request,
        c.snapshot,
        tuple(a.executions),
        a.base.base.loop.store,
        a.base.base.loop.journal.controls,
        c.operation,
        context=c.context,
    )
    assert summary == dict(generations=3, interactions=1, stop_reason="finished")
    assert (
        a.session.calls == 3
        and len(a.base.base.channel.sent) == sent
        and len(a.session.body_calls) == counted
    )
    assert sum(isinstance(x, ReadPlanned) for x in c.snapshot.events) == 1
    (rejected,) = [x for x in c.snapshot.events if isinstance(x, DecisionRejected)]
    assert rejected.decision.failure_ref is not None
    failure = ActorParseFailure.model_validate_json(
        a.base.base.loop.store.read(rejected.decision.failure_ref)
    )
    feedback = ActorProposalFeedback.model_validate_json(failure.message)
    assert (
        feedback.code == code
        and feedback.consecutive_invalid == feedback.repeated_invalid == 1
    )
    middle = a.session.prompts[1]
    assert code in middle.messages[1].content
    assert "consecutive_invalid" not in middle.messages[1].content
    assert middle.observation_view and middle.observation_view.invalid_proposals
    assert middle.observation_view.invalid_proposals.consecutive_invalid == 1
    final = a.session.prompts[-1].observation_view
    assert final and final.reads_used == 1 and final.invalid_proposals
    assert (
        final.invalid_proposals.consecutive_invalid
        == final.invalid_proposals.repeated_invalid
        == 0
    )
    assert "browsergym-adaptive-count-probe-v2" in a.session.complete_inputs
    c.context.clear_inputs()


def test_current_directory_exposes_a_schema_valid_exact_continuation_without_spending_a_read(
    tmp_path: Path,
) -> None:
    index = indexed(
        "[1] RootWebArea\n\t[2] button A\n\t[3] button B\n",
        directory_entries=1,
        **NEW_POLICY,
    )
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ListObservationRegions(
        request_id="directory",
        snapshot=index.snapshot,
        output_tokens=index.policy.body_max_tokens,
    )
    page = reads.automatic_directory(request, op("automatic"), control=case.control)
    assert page.payload.continuation
    body = observation_read_body(
        page.payload,
        current_view="structural_local",
        captured_length=len(index.text),
        read_tools=("list_regions", "read_region", "search_regions"),
    )
    metadata = json.loads(
        next(line for line in body.splitlines() if line.startswith("{"))
    )
    choice = metadata["continuation_read"]
    schemas = materialize_actor_tools(
        ("scroll",),
        ("list_regions", "read_region", "search_regions"),
        index.policy,
        index.snapshot.observation_ref.sha256,
        1,
    )
    assert not actor_schema_violations(
        schemas.require_tool("list_regions", "observation_read")["inputSchema"], choice
    )
    restored = ListObservationRegions(
        request_id="continue",
        snapshot=index.snapshot,
        **{key: value for key, value in choice.items() if key != "snapshot_sha256"},
    )
    assert observation_request_key(
        restored.model_copy(update={"continuation": None})
    ) == observation_request_key(request)
    reads.check_proposal(restored, progress=progress, control=case.control)
    assert not reads._spent and not session.body_calls
    assert "continuation_read" not in observation_read_body(page.payload)
    reads.close()
    case.client.close(case.control)
