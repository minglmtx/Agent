"""Role contract/evidence tests, never model understanding or task success."""

import ast
import hashlib
import json
from pathlib import Path
from typing import cast
import pytest
from pydantic import JsonValue, ValidationError
from lab_generate_skill.actor.instructions import ACTIONS, OBSERVATION_MODE
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.response import parse_actor_action
from lab_generate_skill.domain.browser_action_catalog import declared_signatures
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.teacher_json import object_value, array_value
from lab_generate_skill.domain.teacher_input import native_evidence
from lab_generate_skill.generator.capabilities import actor_capabilities
from lab_generate_skill.generator.instructions import (
    FULL_AX_GUIDANCE,
    VIEWPORT_GUIDANCE,
)
from lab_generate_skill.generator.prompting import prepare_generator
from lab_generate_skill.teacher.field_projection import project_fields
from lab_generate_skill.teacher.instructions import GUIDE, GUIDE_REVISION3
from test_actor_protocol import turn
from test_construction_inputs import generation_input

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
A = W / "experiments/framework-mapdata-trace-analysis-20261101-v1/analysis-4867875"


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
@pytest.mark.parametrize("scope", [FULL_AX_GUIDANCE, VIEWPORT_GUIDANCE, None])
def test_generator_gets_actual_actor_actions_without_claiming_unknown_initial_scope(
    site: Site, scope: str | None
) -> None:
    base = turn()
    task = base.task.model_copy(
        update={"identity": base.task.identity.model_copy(update={"site": site})}
    )
    request = generation_input()
    request = request.model_copy(
        update={"context": request.context.model_copy(update={"task": task})}
    )
    text = json.dumps(
        {"axtree": "[31] button Save", "observation_scope": scope}, ensure_ascii=False
    )
    record = base.observation.record.model_copy(
        update={
            "task": task.identity,
            "context_id": request.context.context_id,
            "text": text,
        }
    )
    actual = prepare_generator(request, ResolvedObservation(record=record, text=text))
    user = json.loads(actual.messages[1].content)
    capabilities = user["actor_capabilities"]
    assert (
        capabilities["actor_observation_mode"]
        == OBSERVATION_MODE
        == "current_page_full_ax"
    )
    assert capabilities["initial_observation_scope"] == (
        "current_page_full_ax"
        if scope == FULL_AX_GUIDANCE
        else "viewport" if scope == VIEWPORT_GUIDANCE else "not_declared"
    )
    assert capabilities["allowed_actions"] == [ACTIONS[n] for n in task.allowed_actions]
    assert capabilities["registered_read_tools"] == []
    assert user["initial_observation"] == text
    assert user["retrieved_skills"] == [
        s.model_payload() for s in request.retrieved_skills
    ]
    assert len(user["retrieved_skills"]) == 6
    assert all(
        set(s) == {"title", "principle", "when_to_apply"}
        for s in user["retrieved_skills"]
    )
    assert "claim_ref" not in actual.input_bytes().decode()
    assert actual == prepare_generator(
        request, ResolvedObservation(record=record, text=text)
    )
    assert all(
        signature
        in prepare_actor(
            base.model_copy(
                update={
                    "task": task,
                    "observation": ResolvedObservation(record=record, text=text),
                }
            )
        )
        .messages[1]
        .content
        for signature in capabilities["allowed_actions"]
    )


@pytest.mark.parametrize(
    "names",
    [None, "", [], (), ("click", "click"), ("read_region",), ("click", 1), (True,)],
)
def test_invalid_or_unregistered_actions_do_not_produce_a_capability_contract(
    names: object,
) -> None:
    with pytest.raises(ValueError):
        declared_signatures(cast(tuple[str, ...], names))


@pytest.mark.parametrize("name", ["read_region", "read_partition", "planner", "stop"])
def test_unregistered_skill_tools_are_not_new_operations(name: str) -> None:
    public = turn().task
    with pytest.raises(ValueError):
        actor_capabilities(
            public.model_copy(update={"allowed_actions": (name,)}), "public"
        )
    with pytest.raises(ValueError):
        parse_actor_action(
            json.dumps(
                {"thought": "Use a suggested skill function", "action": name + '("1")'}
            ),
            "stop",
            public.model_copy(update={"allowed_actions": (name,)}),
            "action",
        )


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "null",
        "{}",
        '{"observation_scope":{}}',
        '{"observation_scope":true}',
        "unread tail",
        "partial: Save",
        "",
    ],
)
def test_partial_empty_or_unrecognized_initial_scope_stays_unknown(text: str) -> None:
    c = actor_capabilities(turn().task, text)
    assert c["initial_observation_scope"] == "not_declared"
    assert c["registered_read_tools"] == []


def test_original_map_wrong_target_remains_original_and_no_partition_is_invented() -> (
    None
):
    result = json.loads((A / "result.json").read_bytes())
    original = result["timeline"][0]
    record = Observation.model_validate_json(
        (A / "turn-01/before-observation.json").read_bytes()
    )
    assert record.text is not None
    assert (
        hashlib.sha256(record.model_dump_json().encode()).hexdigest()
        == original["before_ref"]["sha256"]
    )
    assert (
        hashlib.sha256(record.text.encode()).hexdigest()
        == original["before_text_sha256"]
    )
    assert any(
        "link" in line and "'Layers'" in line for line in record.text.splitlines()
    )
    action = original["action"]
    expression = ast.parse(action["payload"], mode="eval").body
    assert isinstance(expression, ast.Call)
    bid = ast.literal_eval(expression.args[0])
    assert not any(
        line.strip().startswith("[" + bid + "]") and "'Layers'" in line
        for line in record.text.splitlines()
    )
    # Syntax validity is not target correctness. The executor must not silently
    # repair a wrong/stale ID from thought text or substitute a nearby object.
    parsed = parse_actor_action(
        json.dumps({"thought": "Open Layers", "action": action["payload"]}),
        "stop",
        turn().task.model_copy(update={"allowed_actions": (action["name"],)}),
        action["action_id"],
    )
    assert parsed.payload == action["payload"]
    assert actor_capabilities(turn().task, record.text)["registered_read_tools"] == []
    assert (
        result["original_valid_failure"] == "failure/0"
        and result["actual_call_count"] == 0
    )


@pytest.mark.parametrize(
    "returned",
    [
        None,
        {},
        {"range": [], "complete": False},
        {"range": ["tail"], "complete": False, "error": "cancelled"},
    ],
)
@pytest.mark.parametrize("site", ["map", "shopping"])
def test_teacher_keeps_unread_partial_stale_and_posthoc_facts_separate(
    site: str, returned: JsonValue
) -> None:
    # This is a future-read evidence preservation case, not a registered reader.
    initial = f"{site}: [11] button Save in row A; [12] button Save in row B"
    first: dict[str, JsonValue] = {
        "axtree_txt": initial,
        "actor_visible_input": {"text": initial, "snapshot": "v1"},
        "read_request": {"range": "tail", "snapshot": "v1"},
        "read_result": returned,
        "delivered_to_actor": False,
    }
    later: dict[str, JsonValue] = {
        "axtree_txt": "[24] button Save in row B; final answer only later",
        "snapshot": "v2",
        "observation_record_source": "later_terminal_capture",
        "unread_required_fact": "later-only-value",
    }
    evidence: dict[str, JsonValue] = {
        "task": "Save row B",
        "initial_observation": initial,
        "attempts": [
            {
                "candidate_id": "candidate",
                "attempt_id": "attempt",
                "revision_round": 1,
                "trajectory": [
                    {"role": "user", "content": json.dumps(first)},
                    {
                        "role": "assistant",
                        "content": "click proposed",
                        "action_payload": "click('11')",
                        "operation_result": {"status": "unknown", "result": None},
                    },
                    {"role": "user", "content": json.dumps(later)},
                ],
            }
        ],
    }
    payload = project_fields(native_evidence(json.dumps(evidence)))
    attempt = object_value(
        array_value(payload.evidence["attempts"], "attempts")[0], "attempt"
    )
    events = array_value(attempt["events"], "events")
    before = object_value(
        object_value(events[0], "event")["observation"], "observation"
    )
    after = object_value(object_value(events[2], "event")["observation"], "observation")
    assert before["read_result"] == returned and before["delivered_to_actor"] is False
    assert "unread_required_fact" not in before
    assert (
        after["unread_required_fact"] == "later-only-value"
        and "actor_visible_input" not in after
    )
    action = object_value(events[1], "event")
    assert object_value(action["message_extra"], "extra")["operation_result"] == {
        "status": "unknown",
        "result": None,
    }
    assert attempt["candidate_id"] == "candidate" and attempt["revision_round"] == 1
    assert "guide revision 4" in GUIDE and "guide revision 3" in GUIDE_REVISION3
    assert "do not\nput the later answer into the skill" in GUIDE
    assert "successful click return alone does not prove" in GUIDE


def test_conditional_stage_skill_still_uses_only_original_fields_and_limits() -> None:
    s = CompactSkill(
        title="Open the requested page",
        principle=(
            "1. Identify the requested destination by its label and navigation scope; if already visible, select its current control.\n"
            "2. If information is missing, inspect available navigation and confirm the destination before proceeding.\n"
            "3. Check the destination heading and URL; if the panel did not open, inspect the returned state before another action."
        ),
        when_to_apply="Navigating to a named destination from a public page.",
    )
    assert set(s.model_payload()) == {"title", "principle", "when_to_apply"}
    assert CompactSkill.model_validate_json(s.model_dump_json()) == s
    with pytest.raises(ValidationError):
        CompactSkill.model_validate({**s.model_payload(), "steps": []})
