"""Public-only Actor projection, bounded parser and actual saved initial view."""

import hashlib
import ast
import json
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.response import parse_actor_action
from lab_generate_skill.domain.actor_prompt import (
    ActorPublicTurn,
    ActorHistoryItem,
    ActorPrompt,
)
from lab_generate_skill.domain.observation import (
    Observation,
    ResolvedObservation,
    BrowserTab,
)
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.browser_action_protocol import validate_action
from observation_fixtures import sample_observation
from state_contract_fixtures import scope


def test_frozen_system_preserves_legacy_baseline_with_actual_full_ax_scope() -> None:
    from lab_generate_skill.actor.instructions import SYSTEM

    root = Path(__file__).resolve().parents[2] / "src/lab_generate_skill"
    constants: dict[str, str] = {}
    for filename in ("gobrowse_runtime.py", "browser_prompt_contract.py"):
        for node in ast.parse((root / filename).read_text()).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = node.targets[0]
                if isinstance(name, ast.Name) and name.id in (
                    "SYSTEM_PROMPT",
                    "FULL_AX_GUIDANCE",
                    "SKILL_GUIDANCE",
                ):
                    constants[name.id] = ast.literal_eval(node.value)
    assert SYSTEM == "\n".join(
        constants[name]
        for name in ("SYSTEM_PROMPT", "FULL_AX_GUIDANCE", "SKILL_GUIDANCE")
    )


def turn() -> ActorPublicTurn:
    task = PublicTask(
        identity=scope().task,
        goal="Change the public description to 新描述",
        start_url="https://example.org/admin/",
        allowed_actions=("click", "fill", "send_msg_to_user"),
        output_requirements=("Report the observed save result.",),
    )
    observation = sample_observation(task.identity).model_copy(
        update={
            "text": "[1] textbox Description value='old'\n[2] button Save\n  preserve spacing  ",
            "tabs": (BrowserTab(tab_id="main", url=task.start_url, title="Product"),),
        }
    )
    return ActorPublicTurn(
        task=task,
        skill=CompactSkill(
            title="Confirm changes",
            principle="Save once and inspect the returned page.",
            when_to_apply="Editing a visible field.",
        ),
        observation=ResolvedObservation(record=observation, text=observation.text),
        history=(),
        memory=InactivePolicy(
            status="disabled",
            reason="Selected first chain uses baseline action history.",
        ),
    )


def test_public_input_preserves_full_page_skill_history_tabs_and_error() -> None:
    original = turn()
    observed = original.observation.record.model_copy(
        update={"sequence": 1, "last_action_error": "Validation: value rejected"}
    )
    value = original.model_copy(
        update={
            "observation": ResolvedObservation(record=observed, text=observed.text),
            "history": (
                ActorHistoryItem(
                    action="fill('1', 'wrong')", error="Validation: value rejected"
                ),
            ),
        }
    )
    request = prepare_actor(value)
    assert request.messages[0].role == "system" and request.messages[1].role == "user"
    content = request.messages[1].content
    assert (
        original.observation.text is not None and original.observation.text in content
    )
    for item in [
        value.task.goal,
        value.skill.principle,
        value.history[0].action,
        value.history[0].error,
        value.task.output_requirements[0],
    ]:
        assert item in content
    assert '"active": true' in content and '"index": 0' in content
    assert "without viewport" in request.messages[0].content
    assert "goto(url)" not in content and "click(bid)" in content
    wire = request.input_bytes().decode()
    assert set(json.loads(wire)) == {"messages"}
    for forbidden in [
        "source_task_id",
        "attempt_id",
        "recovery_ref",
        "claim_ref",
        "captured_at",
        "memory",
        "prompt_version",
        "schema_version",
    ]:
        assert forbidden not in wire
    assert ActorPrompt.model_validate_json(request.model_dump_json()) == request


@pytest.mark.parametrize(
    "change",
    [
        "private_key",
        "enabled_memory",
        "loading",
        "missing_text",
        "wrong_task",
        "unsupported_action",
        "extra",
        "old_version",
    ],
)
def test_unsupported_public_view_fails_without_silent_projection(change: str) -> None:
    value = turn().model_dump()
    if change == "private_key":
        value["task"]["private_spec_ref"] = "private"
    if change == "enabled_memory":
        value["memory"]["status"] = "enabled"
    if change == "loading":
        value["observation"]["record"]["state"] = "loading"
    if change == "missing_text":
        value["observation"]["text"] = None
    if change == "wrong_task":
        value["observation"]["record"]["task"]["task_id"] = "other"
    if change == "unsupported_action":
        value["task"]["allowed_actions"] = ("custom_action",)
    if change == "extra":
        value["unexpected"] = True
    if change == "old_version":
        value["schema_version"] = "actor-public-turn/0"
    with pytest.raises((ValueError, ValidationError)):
        prepare_actor(cast(ActorPublicTurn, value))


@pytest.mark.parametrize("value", [None, "", 1, (), []])
def test_bad_projection_input_type(value: object) -> None:
    with pytest.raises(ValidationError):
        prepare_actor(cast(ActorPublicTurn, value))


def test_empty_measured_page_remains_empty_and_large_input_rejected() -> None:
    value = turn()
    blank = value.observation.record.model_copy(update={"text": ""})
    request = prepare_actor(
        value.model_copy(
            update={"observation": ResolvedObservation(record=blank, text="")}
        )
    )
    assert (
        "# Current page accessibility tree\n\n\n# Previous actions"
        in request.messages[1].content
    )
    huge = value.observation.record.model_copy(
        update={"text": "界" * (3 * 1024 * 1024)}
    )
    with pytest.raises(ValueError, match="byte budget"):
        prepare_actor(
            value.model_copy(
                update={"observation": ResolvedObservation(record=huge, text=huge.text)}
            )
        )


@pytest.mark.parametrize(
    "text,payload",
    [
        ('{"thought":"Save now","action":"click(\'2\')"}', "click('2')"),
        ("```json\n{\"action\":\"fill('1', '新描述')\"}\n```", "fill('1', '新描述')"),
        (
            '<think>public reasoning</think> {"thought":"Done","action":"send_msg_to_user(\'Saved\')"}',
            "send_msg_to_user('Saved')",
        ),
    ],
)
def test_baseline_literal_action_parsed_and_shared_browser_grammar_accepts(
    text: str, payload: str
) -> None:
    task = turn().task
    action = parse_actor_action(text, "stop", task, "action-1")
    assert action.payload == payload and action.action_id == "action-1"
    validate_action(action, task)


@pytest.mark.parametrize(
    "text,finish",
    [
        ("", "stop"),
        ("not JSON", "stop"),
        ('{"action":"click(\'2\')"}', "length"),
        ('{"action":"click(\'2\')","action":"fill(\'1\',\'x\')"}', "stop"),
        ('{"action":"click(\'2\')","thought":NaN}', "stop"),
        ('{"action":"goto(\'https://bad.example/\')"}', "stop"),
        ('{"action":"__import__(\'os\')"}', "stop"),
        ('{"action":"click(open(\'secret\'))"}', "stop"),
        ("{\"action\":\"click('2'); click('3')\"}", "stop"),
        ('{"action":"browser.click(\'2\')"}', "stop"),
        ("{\"action\":\"click(**{'bid':'2'})\"}", "stop"),
        ("{\"action\":\"fill(bid='1', bid='2')\"}", "stop"),
        ('{"action":null}', "stop"),
        ('{"action":[]}', "stop"),
        ('{"action":"click(\'2\')","thought":3}', "stop"),
        ('{"action":"click(\'2\')","private":1}', "stop"),
        ('{"action":"unknown(\'2\')"}', "stop"),
    ],
)
def test_invalid_response_never_becomes_action(text: str, finish: str) -> None:
    with pytest.raises((ValueError, SyntaxError)):
        parse_actor_action(text, finish, turn().task, "action-1")


@pytest.mark.parametrize("text", [None, 1, b"{}", "x" * (1024 * 1024 + 1)])
def test_response_type_and_byte_limits(text: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        parse_actor_action(cast(str, text), "stop", turn().task, "action-1")


def test_actual_qualified_source_uses_exact_original_public_observation() -> None:
    root = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/check-4772787"
    )
    cas = (
        root
        / "tmp/pytest-of-r102bf10/pytest-0/test_registered_actual_site_an0/evidence/blobs"
    )
    observation_sha = "d76d1bfd5dd9be37d592ba80d7a5053d4d3178457827babf5d9ba276f77861bb"
    context_sha = "7ce66027ac673f3372f45761a956501c1269aba440536e948f74c76e33c72df3"
    obs_raw, context_raw = (cas / observation_sha).read_bytes(), (
        cas / context_sha
    ).read_bytes()
    assert (
        hashlib.sha256(obs_raw).hexdigest() == observation_sha
        and hashlib.sha256(context_raw).hexdigest() == context_sha
    )
    context = json.loads(context_raw)
    observed = Observation.model_validate_json(obs_raw)
    task = PublicTask.model_validate_json(json.dumps(context["task"]))
    value = ActorPublicTurn(
        task=task,
        skill=turn().skill,
        observation=ResolvedObservation(record=observed, text=observed.text),
        history=(),
        memory=turn().memory,
    )
    prompt = prepare_actor(value)
    assert (
        observed.sequence == 0
        and context["initial_observation_ref"]["sha256"] == observation_sha
    )
    assert observed.text is not None and observed.text in prompt.messages[1].content
    assert task.goal in prompt.messages[1].content
    assert "private_spec_ref" not in prompt.input_bytes().decode()
