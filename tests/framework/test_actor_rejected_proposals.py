"""Rejected reads stay unexecuted; bounded durable streak stops the real loop."""

import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.actor.observation_read_response import parse_observation_read
from lab_generate_skill.actor.adaptive_layout import adaptive_frame
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.application.actor_context_preparation import (
    ControlledActorContext,
)
from lab_generate_skill.application.actor_rejection_progress import (
    ActorRepeatedInvalidProposalsStopped,
    check_repeated_invalid_proposals,
)
from lab_generate_skill.adapters.plans.actor_closed_review import review_actor
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.trace_events import (
    ReadPlanned,
    ReadObserved,
    DecisionRejected,
)
from lab_generate_skill.policies.actor_rejected_proposal import (
    rejected_proposal_identity,
)
from adaptive_observation_fixtures import prompt
from adaptive_actor_loop_fixtures import adaptive_loop_case
from observation_read_fixtures import policy
from test_adaptive_context_repair import pure_case
from test_run_journal import command
from retrieval_fixtures import reference


def with_limit(maximum: int) -> ActorPrompt:
    original = prompt()
    assert original.observation_view is not None
    view = original.observation_view
    frozen = view.policy.model_copy(update={"max_ranges": maximum})
    snapshot = view.snapshot.model_copy(update={"policy_sha256": frozen.digest})
    return original.model_copy(
        update={
            "observation_view": view.model_copy(
                update={"policy": frozen, "snapshot": snapshot}
            )
        }
    )


def proposal(
    p: ActorPrompt, count: int, *, thought: str = "Read", output: int = 8
) -> str:
    assert p.observation_view is not None
    return json.dumps(
        dict(
            thought=thought,
            read=dict(
                tool="read_region",
                snapshot_sha256=p.observation_view.snapshot.observation_ref.sha256,
                output_tokens=output,
                ranges=[
                    dict(region_id=f"region-{i}", unit="whole_region")
                    for i in range(count)
                ],
            ),
        )
    )


@pytest.mark.parametrize("maximum,count", [(4, 5), (4, 24), (8, 9), (16, 24)])
def test_effective_policy_precedes_absolute_schema_cap(
    maximum: int, count: int
) -> None:
    p = with_limit(maximum)
    with pytest.raises(ValueError) as caught:
        parse_observation_read(proposal(p, count), "stop", p, request_id="rejected")
    message = str(caught.value)
    assert f"maximum_ranges={maximum}; submitted_ranges={count}" in message
    assert "not executed" in message and "list_regions" in message
    assert "at most 16" not in message


@pytest.mark.parametrize("maximum", [1, 4, 8, 16])
def test_normal_reads_at_current_limit_remain_legal(maximum: int) -> None:
    p = with_limit(maximum)
    result = parse_observation_read(proposal(p, maximum), "stop", p, request_id="read")
    assert result is not None and result.tool == "read_region"
    assert len(result.ranges) == maximum


def test_prompt_declares_same_frozen_limit_and_separate_rejection_threshold() -> None:
    public, _, _, _ = pure_case()
    source = public.observation_source
    assert source is not None
    frozen = source.policy.model_copy(update={"max_ranges": 8})
    changed = source.model_copy(
        update={
            "policy": frozen,
            "snapshot": source.snapshot.model_copy(
                update={"policy_sha256": frozen.digest}
            ),
        }
    )
    system, _, suffix = adaptive_frame(
        public.model_copy(update={"observation_source": changed})
    )
    assert '"maximum_ranges": 8' in suffix
    assert (
        f'"repeated_invalid_proposal_limit": {frozen.consecutive_no_progress}' in suffix
    )
    assert "list_regions before read_region" in system


def completion(p: ActorPrompt, text: str) -> ActorTextCompletion:
    return ActorTextCompletion(
        generation_id="generation",
        request_id="request",
        input_ref=reference(p, "actor-model-input/1"),
        parameters_ref=reference({"parameters": True}, "model-parameters/1"),
        model_input_sha256=hashlib.sha256(p.input_bytes()).hexdigest(),
        text=text,
        finish_reason="stop",
    )


def test_identity_ignores_thought_and_object_order_but_retains_all_read_parameters() -> (
    None
):
    p = with_limit(4)
    a = completion(p, proposal(p, 5))
    changed = json.loads(a.text)
    changed["thought"] = "A different justification"
    b = completion(p, json.dumps(changed, sort_keys=True))
    identity = rejected_proposal_identity(p, a)
    assert identity == rejected_proposal_identity(p, b)
    assert identity != rejected_proposal_identity(
        p, completion(p, proposal(p, 5, output=7))
    )
    assert identity != rejected_proposal_identity(with_limit(8), a)
    assert p.observation_view is not None
    v = p.observation_view
    new = p.model_copy(
        update={
            "observation_view": v.model_copy(
                update={
                    "snapshot": v.snapshot.model_copy(
                        update={"sequence": v.snapshot.sequence + 1}
                    )
                }
            )
        }
    )
    assert identity != rejected_proposal_identity(new, a)


@pytest.mark.parametrize(
    "text",
    ["", "not JSON", '{"read":{"x":1,"x":2}}', '{"read":{"x":NaN}}', '{"read":null}'],
)
def test_malformed_proposals_have_stable_identity_without_execution(text: str) -> None:
    p = with_limit(4)
    assert rejected_proposal_identity(
        p, completion(p, text)
    ) == rejected_proposal_identity(p, completion(p, text))


@pytest.mark.parametrize("limit", [1, 2])
def test_real_rejected_loop_stops_at_frozen_threshold_without_read_or_business_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    import adaptive_actor_loop_fixtures

    monkeypatch.setattr(
        adaptive_actor_loop_fixtures,
        "policy",
        lambda **kw: policy(**kw, consecutive_no_progress=limit),
    )
    c = adaptive_loop_case(tmp_path)

    def infer(
        tokens: tuple[int, ...], parameters: object, control: object
    ) -> LocalActorOutput:
        p = c.session.last_prompt
        assert p is not None
        c.session.prompts.append(p)
        c.session.calls += 1
        return LocalActorOutput(
            text=proposal(p, 5, thought=str(c.session.calls)),
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(c.session, "infer", infer)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    failure = caught.value
    assert isinstance(failure.primary, ActorRepeatedInvalidProposalsStopped)
    assert failure.primary.count == failure.primary.limit == limit
    assert failure.cleanup_errors == () and c.session.calls == limit
    snapshot = failure.snapshot
    assert snapshot is not None
    trace = snapshot.project().sealed
    assert trace is not None and trace.stop_reason == "error"
    assert trace.generations == limit and trace.interactions == 0
    assert sum(isinstance(e, DecisionRejected) for e in snapshot.events) == limit
    assert not any(isinstance(e, (ReadPlanned, ReadObserved)) for e in snapshot.events)
    for p in c.session.prompts:
        assert p.observation_view is not None
        assert p.observation_view.reads_used == p.observation_view.no_progress == 0
    store = c.base.base.loop.store
    for turn in trace.turns:
        assert turn.decision is not None and turn.decision.failure_ref is not None
        fact = ActorParseFailure.model_validate_json(
            store.read(turn.decision.failure_ref)
        )
        assert "maximum_ranges=4; submitted_ranges=5" in fact.message
        assert "executed=false" in fact.message
    controls = c.base.base.loop.journal.controls
    op = command("rejected-review", attempt="attempt", cleanup_parent="original")
    context = c.runner.deps.context
    assert isinstance(context, ControlledActorContext) and context.inputs is not None
    assert isinstance(context.inputs, RecordedActorContextInputs)
    with pytest.raises(EvidenceIntegrityError, match="No complete Actor attempt"):
        review_actor(
            c.request,
            snapshot,
            tuple(c.executions),
            store,
            controls,
            op,
            context=context.inputs,
        )
    original_read = store.read

    def corrupt(ref: object, control: object = None) -> bytes:
        return b"corrupt"

    monkeypatch.setattr(store, "read", corrupt)
    with pytest.raises(EvidenceIntegrityError, match="changed original bytes"):
        check_repeated_invalid_proposals(snapshot, store, controls.bind(op))
    monkeypatch.setattr(store, "read", original_read)
    c.base.base.client.close(
        controls.bind(command("close-rejected-worker", attempt="attempt"))
    )


def test_recovered_invalid_read_is_independently_reviewed_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from adaptive_actor_loop_fixtures import AdaptiveSession
    from adaptive_actor_review_fixtures import closed_adaptive_review
    from lab_generate_skill.domain.actor_engine import LocalActorParameters
    from lab_generate_skill.ports.lifecycle import OperationControl

    original = AdaptiveSession.infer

    def infer(
        self: AdaptiveSession,
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        if self.calls:
            return original(self, tokens, parameters, control)
        p = self.last_prompt
        assert p is not None
        self.calls += 1
        self.prompts.append(p)
        return LocalActorOutput(
            text=proposal(p, 5),
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(AdaptiveSession, "infer", infer)
    c = closed_adaptive_review(tmp_path)
    a = c.actor
    sent = len(a.base.base.channel.sent)
    summary = review_actor(
        a.request,
        c.snapshot,
        tuple(a.executions),
        a.base.base.loop.store,
        a.base.base.loop.journal.controls,
        c.operation,
        context=c.context,
    )
    assert summary == dict(generations=2, interactions=1, stop_reason="finished")
    assert a.session.calls == 2 and len(a.base.base.channel.sent) == sent
    assert a.session.closed == 1
    assert (
        "maximum_ranges=4; submitted_ranges=5"
        in a.session.prompts[-1].messages[1].content
    )
