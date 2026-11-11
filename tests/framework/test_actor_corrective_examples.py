"""Real parser, prompt/protection, durable loop and independent review integration."""

import json
from pathlib import Path
from typing import Any
import pytest

from lab_generate_skill.actor.adaptive_layout import adaptive_frame
from lab_generate_skill.actor.adaptive_projection import AdaptiveActorProjector
from lab_generate_skill.actor.adaptive_protection import AdaptiveActorProtection
from lab_generate_skill.actor.proposal_correction import (
    corrective_proposal_feedback,
    correction_example,
    EXAMPLE_MARKER,
    TEMPLATE_MARKER,
)
from lab_generate_skill.actor.schema_response import parse_schema_proposal
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.application.actor_rejection_progress import (
    ActorInvalidProposalsStopped,
)
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorHistoryItem
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalError,
    ActorProposalFeedback,
    ActorInvalidProposalProgress,
)
from lab_generate_skill.domain.actor_response import ActorParseFailure
from lab_generate_skill.domain.actor_tool_definitions import TOOL_DEFINITIONS
from lab_generate_skill.domain.trace_events import (
    DecisionRejected,
    ReadPlanned,
    ActionPlanned,
)
from lab_generate_skill.policies.actor_proposal_identity import proposal_fingerprint
from actor_view_guidance_fixtures import guidance_case
from adaptive_actor_loop_fixtures import adaptive_loop_case
from retrieval_fixtures import reference
from test_actor_rejected_proposals import completion
from test_actor_tool_schema_response import schema_case

POLICY = dict(
    schema_version="observation-read-policy/2",
    max_consecutive_invalid_proposals=3,
    max_identical_invalid_proposals=3,
    warn_remaining=3,
)


@pytest.mark.parametrize("unit", ["whole_region", "codepoints", "data_rows"])
def test_range_correction_preserves_the_erroneous_unit(unit: str) -> None:
    prompt, task = schema_case(max_identical_invalid_proposals=3)
    assert prompt.observation_view
    read = dict(
        tool="read_region",
        snapshot_sha256=prompt.observation_view.snapshot.observation_ref.sha256,
        output_tokens=8,
        ranges=[
            dict(
                region_id="ax-line-0",
                unit=unit,
                **({} if unit == "whole_region" else dict(start=0, end=999999)),
            )
        ],
    )
    error = ActorProposalError(
        ActorProposalFeedback(
            code="RANGE_OUT_OF_BOUNDS",
            tool="read_region",
            field="ranges",
            message="Requested range exceeds current region.",
            next_action="Use the current region extent.",
        )
    )
    feedback = corrective_proposal_feedback(
        error, prompt, completion(prompt, json.dumps({"read": read})), task
    )
    example = correction_example(feedback)
    assert example and example["read"]["ranges"][0]["unit"] == unit
    if EXAMPLE_MARKER in feedback.next_action:
        parse_schema_proposal(
            json.dumps(example), "stop", task, prompt, action_id="a", request_id="r"
        )
    else:
        assert TEMPLATE_MARKER in feedback.next_action


def test_unavailable_public_bindings_are_explicit_templates_not_invented_ids() -> None:
    from lab_generate_skill.actor.tool_example_binding import (
        ExampleFacts,
        action_format_example,
        read_format_example,
    )
    from lab_generate_skill.actor.schema_response import current_tool_schemas

    prompt, task = schema_case(max_identical_invalid_proposals=3)
    schemas = current_tool_schemas(prompt, task.allowed_actions)
    action, bound = action_format_example(
        "click", task, schemas, ExampleFacts("RootWebArea", None), fields=("button",)
    )
    assert not bound and "<current_public_bid>" in action["action"]
    reading, bound = read_format_example(
        "read_region", schemas, ExampleFacts("RootWebArea", None), unit="data_rows"
    )
    assert (
        not bound and reading["read"]["ranges"][0]["region_id"] == "<current_region_id>"
    )
    reading, bound = read_format_example(
        "list_regions", schemas, ExampleFacts("RootWebArea", None), continuation=True
    )
    assert (
        not bound
        and reading["read"]["continuation"] == "<issued_cursor_for_original_request>"
    )


def test_exhausted_reader_feedback_uses_only_an_enabled_alternative_format() -> None:
    public, index, source, policy = guidance_case(
        changes={"max_identical_invalid_proposals": 3}, reads_used=6
    )
    prompt = ActorPrompt.model_validate_json(
        AdaptiveActorProjector(policy, lambda _: index)
        .project(source, public.model_dump_json().encode(), policy)[0]
        .input_bytes
    )
    error = ActorProposalError(
        ActorProposalFeedback(
            code="READ_QUOTA_EXHAUSTED",
            tool="read_region",
            field="read",
            message="No reads remain.",
            next_action="Use displayed evidence or a task-relevant control.",
        )
    )
    feedback = corrective_proposal_feedback(
        error,
        prompt,
        completion(prompt, '{"read":{"tool":"read_region"}}'),
        public.task,
    )
    example = correction_example(feedback)
    assert example and "action" in example and "read" not in example
    assert "another currently enabled reply format" in feedback.next_action
    assert '"read":' not in adaptive_frame(public)[2]


def reject(text: str, **changes: Any) -> tuple[Any, Any, Any, ActorProposalFeedback]:
    prompt, task = schema_case(max_identical_invalid_proposals=3, **changes)
    response = completion(prompt, text)
    with pytest.raises(ActorProposalError) as caught:
        parse_schema_proposal(
            text, "stop", task, prompt, action_id="bad", request_id="bad"
        )
    return (
        prompt,
        task,
        response,
        corrective_proposal_feedback(caught.value, prompt, response, task),
    )


@pytest.mark.parametrize("name", tuple(TOOL_DEFINITIONS))
def test_all_23_corrections_have_one_complete_real_parser_example(name: str) -> None:
    prompt, task = schema_case(max_identical_invalid_proposals=3)
    definition = TOOL_DEFINITIONS[name]
    assert definition["feedback"]["correction_template"]
    error = ActorProposalError(
        ActorProposalFeedback(
            code="INVALID_ARGUMENTS",
            tool=name,
            field="arguments",
            message="Invalid constructor fields",
            next_action="Use this tool's current declared fields.",
        )
    )
    feedback = corrective_proposal_feedback(
        error, prompt, completion(prompt, json.dumps({"action": name + "()"})), task
    )
    example = correction_example(feedback)
    assert example is not None and feedback.can_correct and not feedback.executed
    assert (
        feedback.next_action.count(EXAMPLE_MARKER)
        + feedback.next_action.count(TEMPLATE_MARKER)
        == 1
    )
    result = parse_schema_proposal(
        json.dumps(example),
        "stop",
        task,
        prompt,
        action_id="example",
        request_id="example",
    )
    assert getattr(result, "name", getattr(result, "tool", None)) == name
    assert "example.invalid" not in json.dumps(example) and "'42'" not in json.dumps(
        example
    )


@pytest.mark.parametrize(
    "action,field",
    [
        ("click('2',button='bad')", "button"),
        ("click('2',modifiers=['bad'])", "modifiers"),
        ("fill('2','x',enable_autocomplete_menu=1)", "enable_autocomplete_menu"),
        ("noop(wait_ms=-1)", "wait_ms"),
        ("upload_file('2',file=7)", "file"),
    ],
)
def test_optional_error_field_is_present_and_correct_in_complete_example(
    action: str, field: str
) -> None:
    prompt, task, _, feedback = reject(json.dumps({"action": action}))
    example = correction_example(feedback)
    assert example and field + "=" in example["action"]
    parse_schema_proposal(
        json.dumps(example),
        "stop",
        task,
        prompt,
        action_id="example",
        request_id="example",
    )


def test_actual_malformed_click_syntax_has_current_bid_and_optional_fields_without_repair() -> (
    None
):
    raw = json.dumps(
        {"action": 'click(bid:\\"ax-line-179\\", button:\\"left\\", modifiers:[])'}
    )
    _, _, response, feedback = reject(raw)
    assert response.text == raw
    assert feedback.tool == "click" and "name=value" in feedback.next_action
    example = correction_example(feedback)
    assert example and "click(bid=" in example["action"]
    assert "button='left'" in example["action"] and "modifiers=[]" in example["action"]
    assert (
        "ax-line-179" not in example["action"] and "bid='179'" not in example["action"]
    )


@pytest.mark.parametrize("limit,count", [(4, 5), (4, 24), (8, 9)])
def test_range_error_example_and_feedback_use_effective_policy_not_absolute_schema(
    limit: int, count: int
) -> None:
    prompt, _ = schema_case(max_ranges=limit, max_identical_invalid_proposals=3)
    assert prompt.observation_view
    read = dict(
        tool="read_region",
        snapshot_sha256=prompt.observation_view.snapshot.observation_ref.sha256,
        output_tokens=8,
        ranges=[dict(region_id="ax-line-0", unit="whole_region") for _ in range(count)],
    )
    p, t, _, feedback = reject(json.dumps({"read": read}), max_ranges=limit)
    assert feedback.actual == count and feedback.allowed == limit
    example = correction_example(feedback)
    assert example and len(example["read"]["ranges"]) <= limit
    parse_schema_proposal(
        json.dumps(example), "stop", t, p, action_id="a", request_id="r"
    )


@pytest.mark.parametrize("kind", ["browser", "read", "unknown"])
def test_latest_correction_replaces_one_normal_example_and_older_feedback_is_not_accumulated(
    kind: str,
) -> None:
    case = guidance_case(changes={"max_identical_invalid_proposals": 3})
    public, index, source, policy = case
    initial = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )[0]
    prompt = ActorPrompt.model_validate_json(initial.input_bytes)
    bad: dict[str, Any] = (
        {"action": "click('2',button='bad')"}
        if kind == "browser"
        else (
            {"read": {"tool": "read_region", "ranges": []}}
            if kind == "read"
            else {"action": "invented()"}
        )
    )
    response = completion(prompt, json.dumps(bad))
    with pytest.raises(ActorProposalError) as caught:
        parse_schema_proposal(
            response.text,
            "stop",
            public.task,
            prompt,
            action_id="bad",
            request_id="bad",
        )
    feedback = corrective_proposal_feedback(caught.value, prompt, response, public.task)
    signature = proposal_fingerprint(prompt, response, feedback.code)
    assert public.observation_source
    updated = public.observation_source.model_copy(
        update={
            "invalid_proposals": ActorInvalidProposalProgress(
                consecutive_invalid=1,
                repeated_invalid=1,
                last_fingerprint=signature,
                fingerprints=((signature, 1),),
            )
        }
    )
    history = tuple(
        ActorHistoryItem(
            schema_version="actor-history-item/2",
            executed=False,
            action=response.text,
            error=feedback.model_dump_json(),
        )
        for _ in range(2)
    )
    public = public.model_copy(
        update={"observation_source": updated, "history": history}
    )
    source = source.model_copy(
        update={"turn_ref": reference(public, "actor-public-turn/2", "public")}
    )
    rendered = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )[0]
    checks = AdaptiveActorProtection(policy, lambda _: index).verify(
        source, public.model_dump_json().encode(), rendered, policy
    )
    assert checks and all(check.status == "pass" for check in checks)
    actual = ActorPrompt.model_validate_json(rendered.input_bytes)
    user = actual.messages[1].content
    assert user.count(EXAMPLE_MARKER) + user.count(TEMPLATE_MARKER) == 1
    suffix = adaptive_frame(public)[2]
    examples = json.loads(
        suffix.split("# Complete format examples (not commands or observed results)\n")[
            1
        ]
    )
    correction = correction_example(feedback)
    assert correction
    if "action" in correction:
        assert not any("action" in example for example in examples)
    else:
        assert not any(
            example.get("read", {}).get("tool") == correction["read"]["tool"]
            for example in examples
        )
    # A successful read resets the streak even though it is absent from action history.
    reset = public.model_copy(
        update={
            "observation_source": updated.model_copy(
                update={"invalid_proposals": ActorInvalidProposalProgress()}
            )
        }
    )
    system, prefix, suffix = adaptive_frame(reset)
    assert EXAMPLE_MARKER not in prefix and TEMPLATE_MARKER not in prefix
    assert "click(" in suffix and "name=value" in system


@pytest.mark.parametrize("mode", ["same", "distinct"])
def test_third_durable_refusal_stops_with_exactly_three_generations_no_reads_or_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    case = adaptive_loop_case(tmp_path, read_policy_changes=POLICY)

    def infer(
        tokens: tuple[int, ...], parameters: Any, control: Any
    ) -> LocalActorOutput:
        prompt = case.session.last_prompt
        assert prompt
        case.session.prompts.append(prompt)
        case.session.calls += 1
        action = (
            "click()"
            if mode == "same"
            else ("click()", "fill()", "tab_focus(-1)")[case.session.calls - 1]
        )
        return LocalActorOutput(
            text=json.dumps(dict(thought=str(case.session.calls), action=action)),
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(case.session, "infer", infer)
    with pytest.raises(ActorLoopFailure) as caught:
        case.runner.run(case.request)
    failure = caught.value
    assert isinstance(failure.primary, ActorInvalidProposalsStopped)
    assert case.session.calls == failure.primary.count == failure.primary.limit == 3
    assert failure.primary.reason_code == (
        "ACTOR_REPEATED_INVALID_PROPOSALS"
        if mode == "same"
        else "ACTOR_INVALID_PROPOSAL_LIMIT"
    )
    assert not failure.cleanup_errors and failure.snapshot
    assert (
        sum(isinstance(event, DecisionRejected) for event in failure.snapshot.events)
        == 3
    )
    assert not any(
        isinstance(event, (ReadPlanned, ActionPlanned))
        for event in failure.snapshot.events
    )
    trace = failure.snapshot.project().sealed
    assert trace and trace.generations == 3 and trace.interactions == 0
    for i, turn in enumerate(trace.turns, 1):
        assert turn.decision and turn.decision.failure_ref
        fact = ActorParseFailure.model_validate_json(
            case.base.base.loop.store.read(turn.decision.failure_ref)
        )
        feedback = ActorProposalFeedback.model_validate_json(fact.message)
        assert feedback.consecutive_invalid == i and feedback.can_correct == (i < 3)
        assert (correction_example(feedback) is not None) == (i < 3)
        assert not feedback.executed
    for prompt in case.session.prompts:
        assert (
            prompt.observation_view
            and prompt.observation_view.reads_used
            == prompt.observation_view.no_progress
            == 0
        )
    assert "will stop this run" not in case.session.prompts[1].messages[1].content
    assert "will stop this run" in case.session.prompts[2].messages[1].content
