"""The real new parser consumes the one frozen catalog and effective policies."""

import inspect
import json
from pathlib import Path
from typing import Any
import pytest

from lab_generate_skill.actor.adaptive_projection import AdaptiveActorProjector
from lab_generate_skill.actor.schema_response import parse_schema_proposal
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalError
from lab_generate_skill.domain.actor_tool_definitions import TOOL_DEFINITIONS
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.policies.actor_proposal_identity import proposal_fingerprint
from actor_view_guidance_fixtures import guidance_case
from retrieval_fixtures import reference
from test_actor_rejected_proposals import completion

CATALOG = (
    Path(__file__).resolve().parents[4]
    / "experiments/framework-combined-release-20261030-v1/actor-tool-schema-source-4973433/frozen-inputs/actor-tool-schemas-20261110.json"
)


def schema_case(**changes: Any) -> tuple[ActorPrompt, PublicTask]:
    public, index, source, policy = guidance_case(changes=changes)
    task = public.task.model_copy(
        update={
            "allowed_actions": tuple(
                name
                for name, item in TOOL_DEFINITIONS.items()
                if item["kind"] == "browser_action"
            )
        }
    )
    public = public.model_copy(update={"task": task})
    source = source.model_copy(
        update={"turn_ref": reference(public, "actor-public-turn/2", "public")}
    )
    draft = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )[0]
    return ActorPrompt.model_validate_json(draft.input_bytes), task


def parse(text: str, **changes: Any) -> Any:
    prompt, task = schema_case(**changes)
    return parse_schema_proposal(
        text, "stop", task, prompt, action_id="schema-action", request_id="schema-read"
    )


@pytest.mark.parametrize("name", tuple(TOOL_DEFINITIONS))
def test_all_23_frozen_examples_use_the_actual_parser_and_exact_native_signatures(
    name: str,
) -> None:
    from importlib import import_module

    functions = import_module("browsergym.core.action.functions")

    catalog = json.loads(CATALOG.read_bytes())
    tool = next(tool for tool in catalog["tools"] if tool["name"] == name)
    assert TOOL_DEFINITIONS[name]["inputSchema"] == tool["inputSchema"]
    prompt, task = schema_case()
    example = tool["wire"]["example_response"]
    if tool["kind"] == "browser_action":
        assert tuple(inspect.signature(getattr(functions, name)).parameters) == tuple(
            tool["argument_order"]
        )
    else:
        example["read"]["snapshot_sha256"] = (
            prompt.observation_view.snapshot.observation_ref.sha256
            if prompt.observation_view
            else ""
        )
    result = parse_schema_proposal(
        json.dumps(example),
        "stop",
        task,
        prompt,
        action_id="example",
        request_id="example",
    )
    assert (
        result.name == name
        if isinstance(result, BrowserAction)
        else result.tool == name
    )


@pytest.mark.parametrize(
    "action",
    [
        "fill('node-name','')",
        "select_option('node-name',[])",
        "select_option('node-name','')",
        "upload_file('node-name',[])",
        "send_msg_to_user('')",
        "report_infeasible('')",
        "click('node-name',button='middle',modifiers=['Alt','Shift'])",
        "fill('node-name','x',enable_autocomplete_menu=True)",
        "noop(wait_ms=0)",
        "scroll(-1.5,123456789)",
        "upload_file(bid='node-name',file='permitted-instance-file')",
    ],
)
def test_original_legal_empty_values_native_keywords_and_unbounded_finite_scroll(
    action: str,
) -> None:
    result = parse(json.dumps({"action": action}))
    assert isinstance(result, BrowserAction)


@pytest.mark.parametrize(
    "action",
    [
        "click()",
        "click('x',bid='y')",
        "click('x',bogus=0)",
        "click(*['x'])",
        "click(**{'bid':'x'})",
        "click(str(1))",
        "click('x');noop()",
        "click('x',button='bad')",
        "click('x',modifiers=['Bad'])",
        "fill('x','v',enable_autocomplete_menu=1)",
        "tab_focus(True)",
        "tab_focus(1.0)",
        "tab_focus(1)",
        "noop(-1)",
        "scroll(1e309,0)",
        "scroll(True,0)",
        "upload_file('x',file_or_list=[])",
        "fill('x',b'bad')",
        "fill('x',1j)",
    ],
)
def test_invalid_argument_bindings_are_bounded_correctable_errors(action: str) -> None:
    with pytest.raises(ActorProposalError) as caught:
        parse(json.dumps({"thought": "Do not execute", "action": action}))
    feedback = caught.value.feedback
    assert feedback.code == "INVALID_ARGUMENTS" and not feedback.executed
    assert len(feedback.model_dump_json().encode()) <= 8192


@pytest.mark.parametrize(
    "text,code",
    [
        ("", "INVALID_JSON"),
        ('prefix {"action":"noop()"}', "INVALID_JSON"),
        ('{"action":"noop()"} trailing', "INVALID_JSON"),
        ('{"thought":"a","thought":"b","action":"noop()"}', "INVALID_JSON"),
        ('{"read":{"tool":"x","tool":"y"}}', "INVALID_JSON"),
        ('{"thought":NaN,"action":"noop()"}', "INVALID_JSON"),
        ('{"thought":1e309,"action":"noop()"}', "INVALID_JSON"),
        ('{"thought":"\\ud800","action":"noop()"}', "INVALID_JSON"),
        ("[]", "INVALID_RESPONSE_SHAPE"),
        ("{}", "INVALID_RESPONSE_SHAPE"),
        ('{"action":"noop()","read":{}}', "INVALID_RESPONSE_SHAPE"),
        ('{"action":"noop()","extra":1}', "INVALID_RESPONSE_SHAPE"),
        ('{"action":{}}', "INVALID_ARGUMENTS"),
        ('{"action":"read_region()"}', "WRONG_TOOL_BRANCH"),
        ('{"action":"unknown()"}', "UNKNOWN_TOOL"),
        ('{"read":{"tool":"click"}}', "WRONG_TOOL_BRANCH"),
    ],
)
def test_strict_json_envelope_and_branch_errors_are_explicit(
    text: str, code: str
) -> None:
    with pytest.raises(ActorProposalError) as caught:
        parse(text)
    assert caught.value.feedback.code == code


@pytest.mark.parametrize("limit,count", [(1, 2), (4, 5), (4, 24), (8, 9)])
def test_effective_range_limit_precedes_absolute_cap(limit: int, count: int) -> None:
    prompt, task = schema_case(max_ranges=limit)
    assert prompt.observation_view
    value = {
        "read": {
            "tool": "read_region",
            "snapshot_sha256": prompt.observation_view.snapshot.observation_ref.sha256,
            "output_tokens": 8,
            "ranges": [
                {"region_id": f"ax-line-{n}", "unit": "whole_region"}
                for n in range(count)
            ],
        }
    }
    with pytest.raises(ActorProposalError) as caught:
        parse_schema_proposal(
            json.dumps(value), "stop", task, prompt, action_id="a", request_id="r"
        )
    assert caught.value.feedback.code == "RANGE_COUNT_EXCEEDED"
    assert (
        caught.value.feedback.actual == count and caught.value.feedback.allowed == limit
    )


def test_original_parameter_identity_ignores_thought_order_and_positional_spelling_but_not_duplicates() -> (
    None
):
    prompt, _ = schema_case()
    a = completion(prompt, json.dumps({"thought": "A", "action": "fill('x', '')"}))
    b = completion(
        prompt, json.dumps({"action": "fill(value='',bid='x')", "thought": "B"})
    )
    assert proposal_fingerprint(prompt, a, "INVALID_ARGUMENTS") == proposal_fingerprint(
        prompt, b, "INVALID_ARGUMENTS"
    )
    duplicate = completion(
        prompt, "{\"action\":\"fill('x','')\",\"action\":\"fill('x','')\"}"
    )
    assert proposal_fingerprint(prompt, a, "INVALID_JSON") != proposal_fingerprint(
        prompt, duplicate, "INVALID_JSON"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"tool": "read_region", "ranges": []},
        json.dumps({"tool": "read_region", "ranges": []}),
        "{'tool':'read_region','ranges':[]}",
        "observation.read_region([])",
    ],
)
def test_read_tool_objects_and_strings_in_action_explain_the_correct_branch(
    payload: Any,
) -> None:
    with pytest.raises(ActorProposalError) as caught:
        parse(json.dumps({"action": payload}))
    assert caught.value.feedback.code == "WRONG_TOOL_BRANCH"
    assert "read object" in caught.value.feedback.next_action


def test_original_third_response_receives_branch_feedback_without_rewriting_it() -> (
    None
):
    from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
    from lab_generate_skill.adapters.processes.deadline import DeadlineControl
    from lab_generate_skill.domain.actor_response import ActorTextCompletion
    from lab_generate_skill.domain.evidence import EvidenceRef

    root = (
        Path(__file__).resolve().parents[4]
        / "experiments/framework-combined-release-20261030-v1"
    )
    replay = json.loads(
        (root / "actor-tool-schema-closure-4973709/replay.json").read_bytes()
    )
    original = json.loads(
        (root / "finite-repair-results-4971356/map-4971355-outputs.json").read_bytes()
    )
    store = ReadOnlyEvidence(
        Path(original["root"]) / "evidence",
        max_object_bytes=2 * 1024**2,
        reuse_within_proof=True,
    )
    reference = EvidenceRef.model_validate(replay["rows"][2]["original_response_ref"])
    raw = store.read(reference, DeadlineControl(60, "saved-third-response-parser"))
    saved = ActorTextCompletion.model_validate_json(raw)
    # This is a parser-only comparison on a compatible software task, not a
    # completion rebind or a new dispatch under the original instance.
    with pytest.raises(ActorProposalError) as caught:
        parse(saved.text)
    assert (
        caught.value.feedback.code == "WRONG_TOOL_BRANCH"
    ), caught.value.feedback.model_dump()
    assert saved.model_dump_json().encode() == raw


def test_existing_action_payload_limit_is_a_correctable_input_boundary() -> None:
    with pytest.raises(ActorProposalError) as caught:
        parse(json.dumps({"action": "fill('x'," + repr("v" * 66000) + ")"}))
    assert caught.value.feedback.code == "INVALID_ARGUMENTS"
    assert (
        caught.value.feedback.field == "action"
        and caught.value.feedback.allowed == 65536
    )


@pytest.mark.parametrize(
    "action",
    [
        "fill('x',1e309)",
        "fill('x',b'bad')",
        "fill('x',1j)",
        "fill('x',...)",
        "click(??? )",
        "click('x',bid='x')",
        "unknown(1)",
    ],
)
def test_invalid_action_identity_ignores_thought_even_when_literal_or_syntax_is_invalid(
    action: str,
) -> None:
    prompt, _ = schema_case()
    a = completion(prompt, json.dumps({"thought": "First", "action": action}))
    b = completion(
        prompt, json.dumps({"action": action, "thought": "Different"}, sort_keys=True)
    )
    assert proposal_fingerprint(prompt, a, "INVALID_ARGUMENTS") == proposal_fingerprint(
        prompt, b, "INVALID_ARGUMENTS"
    )


@pytest.mark.parametrize(
    "name",
    tuple(
        name
        for name, definition in TOOL_DEFINITIONS.items()
        if definition["kind"] == "browser_action"
    ),
)
def test_actual_prompt_example_uses_the_schema_when_only_one_native_tool_is_enabled(
    name: str,
) -> None:
    from lab_generate_skill.actor.protocol_examples import action_example

    public, index, source, policy = guidance_case()
    task = public.task.model_copy(update={"allowed_actions": (name,)})
    public = public.model_copy(update={"task": task})
    source = source.model_copy(
        update={"turn_ref": reference(public, "actor-public-turn/2", "public")}
    )
    candidate = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )[0]
    prompt = ActorPrompt.model_validate_json(candidate.input_bytes)
    example = action_example(public)
    result = parse_schema_proposal(
        json.dumps(example),
        "stop",
        task,
        prompt,
        action_id="actual-example",
        request_id="actual-example",
    )
    assert isinstance(result, BrowserAction) and result.name == name
    if name == "upload_file":
        assert "file_or_list" not in prompt.messages[0].content
        assert result.payload.endswith("file=[])")


@pytest.mark.parametrize("tool", ["read_region", "list_regions", "search_regions"])
def test_malformed_region_names_explain_the_current_public_directory(tool: str) -> None:
    prompt, task = schema_case()
    assert prompt.observation_view
    value: dict[str, Any] = dict(
        tool=tool,
        snapshot_sha256=prompt.observation_view.snapshot.observation_ref.sha256,
        output_tokens=8,
    )
    if tool == "read_region":
        value["ranges"] = [dict(region_id="heading-111", unit="whole_region")]
    elif tool == "list_regions":
        value["parent_region_id"] = "heading-111"
    else:
        value.update(query="known", region_ids=["heading-111"])
    with pytest.raises(ActorProposalError) as caught:
        parse_schema_proposal(
            json.dumps({"read": value}),
            "stop",
            task,
            prompt,
            action_id="a",
            request_id="r",
        )
    assert caught.value.feedback.code == "UNKNOWN_REGION"


@pytest.mark.parametrize(
    "name",
    tuple(
        name
        for name, definition in TOOL_DEFINITIONS.items()
        if definition["kind"] == "browser_action"
    ),
)
def test_selected_native_mapper_preserves_schema_example_arguments_without_executing(
    name: str,
) -> None:
    import ast
    from importlib import import_module
    from lab_generate_skill.adapters.browsergym.actions import action_set, map_action

    functions = import_module("browsergym.core.action.functions")
    catalog = json.loads(CATALOG.read_bytes())
    tool = next(tool for tool in catalog["tools"] if tool["name"] == name)
    payload = tool["wire"]["example_response"]["action"]
    mapped = map_action(action_set(1500), payload, 1500)
    original = ast.parse(payload, mode="eval").body
    last = ast.parse(mapped).body[-1]
    assert (
        isinstance(original, ast.Call)
        and isinstance(last, ast.Expr)
        and isinstance(last.value, ast.Call)
    )
    native = last.value
    assert isinstance(native.func, ast.Name) and native.func.id == name
    signature = inspect.signature(getattr(functions, name))

    def bound(call: ast.Call) -> dict[str, Any]:
        result = signature.bind(
            *[ast.literal_eval(item) for item in call.args],
            **{
                key.arg: ast.literal_eval(key.value)
                for key in call.keywords
                if key.arg is not None
            },
        )
        result.apply_defaults()
        return dict(result.arguments)

    assert bound(original) == bound(native)
