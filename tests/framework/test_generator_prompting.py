"""Exact v5 field reuse plus explicitly versioned v6 capability additions."""

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.generator.prompting import prepare_generator
from lab_generate_skill.generator.instructions import (
    FULL_AX_GUIDANCE,
    VIEWPORT_GUIDANCE,
    UNKNOWN_SCOPE_GUIDANCE,
    CAPABILITY_GUIDANCE,
    PROMPT_VERSION,
)
from lab_generate_skill.policies.skill_stage_guidance import STAGE_GUIDANCE
from lab_generate_skill.generator.capabilities import actor_capabilities
from test_construction_inputs import generation_input
from observation_fixtures import sample_observation


def legacy_function() -> Any:
    root = Path(__file__).resolve().parents[2] / "src/lab_generate_skill"
    pins = re.findall(
        r"# Original (\S+) SHA256 ([0-9a-f]{64})",
        (root / "generator/instructions.py").read_text(),
    )
    assert len(pins) == 3
    # Explicit immutable pre-SFT reference. The current generator_sft.py now
    # includes accepted SFT changes; do not rewrite the historical whole-file
    # pins to pretend that it is still the original v5 source.
    root = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/code/"
        "lab-generate-skill-actor64-runtime-candidate-20261101/src/lab_generate_skill"
    )
    for filename, digest in pins:
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == digest
    values: dict[str, Any] = {"json": json}
    names = {
        "PROMPT_VERSION",
        "OPERATIONAL_SKILL_GUIDANCE",
        "SYSTEM",
        "VIEWPORT_GUIDANCE",
        "FULL_AX_GUIDANCE",
        "SKILL_GUIDANCE",
        "SKILL_LENGTH_INSTRUCTIONS",
        "FIELDS",
    }
    for filename in (
        "browser_prompt_contract.py",
        "skill_budget.py",
        "generator_sft.py",
    ):
        tree = ast.parse((root / filename).read_text())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in names for t in node.targets
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        values[target.id] = ast.literal_eval(node.value)
    tree = ast.parse((root / "generator_sft.py").read_text())
    nodes: list[ast.stmt] = [
        n
        for n in tree.body
        if isinstance(n, ast.AugAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "SYSTEM"
        or isinstance(n, ast.FunctionDef)
        and n.name == "generator_messages"
    ]
    exec(
        compile(
            ast.Module(body=nodes, type_ignores=[]),
            "legacy-generator-v5-parity",
            "exec",
        ),
        values,
    )
    return values["generator_messages"]


@pytest.mark.parametrize(
    "text",
    [
        "AX page",
        " 中文\n[1] button Save\n",
        json.dumps(
            {"observation_scope": FULL_AX_GUIDANCE, "axtree": "[1] button Save"}
        ),
        "[]",
        '{"other":"value"}',
    ],
)
def test_message_bytes_preserve_original_public_projection(text: str) -> None:
    request = generation_input()
    record = sample_observation(
        request.context.task.identity, request.context.context_id
    ).model_copy(update={"text": text})
    result = prepare_generator(request, ResolvedObservation(record=record, text=text))
    expected = legacy_function()(
        request.context.task.goal,
        text,
        [s.model_payload() for s in request.retrieved_skills],
    )
    scope = json.loads(text).get("observation_scope") if text.startswith("{") else None
    if scope != FULL_AX_GUIDANCE and scope != VIEWPORT_GUIDANCE:
        expected[0]["content"] = expected[0]["content"].replace(
            VIEWPORT_GUIDANCE, UNKNOWN_SCOPE_GUIDANCE
        )
    expected[0]["content"] += "\n" + STAGE_GUIDANCE + "\n" + CAPABILITY_GUIDANCE
    original_user = json.loads(expected[1]["content"])
    expected[1]["content"] = json.dumps(
        {
            "task": original_user["task"],
            "initial_observation": original_user["initial_observation"],
            "actor_capabilities": actor_capabilities(request.context.task, text),
            "retrieved_skills": original_user["retrieved_skills"],
        },
        ensure_ascii=False,
    )
    assert [m.model_dump() for m in result.messages] == expected
    assert (
        result.input_bytes()
        == json.dumps({"messages": expected}, ensure_ascii=False).encode()
    )
    assert (
        result.generation_input_sha256
        == hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    )
    assert result.generation_input_sha256 != result.model_input_sha256
    user = json.loads(result.messages[1].content)
    assert set(user) == {
        "task",
        "initial_observation",
        "retrieved_skills",
        "actor_capabilities",
    }
    assert (
        result.prompt_version
        == PROMPT_VERSION
        == "webarena-generator-v6-actor-capabilities"
    )
    assert user["retrieved_skills"] == [
        s.model_payload() for s in request.retrieved_skills
    ]
    assert result.seed == request.seed and result.temperature == request.temperature


@pytest.mark.parametrize(
    "fault",
    ["empty", "blank", "loading", "sequence", "context", "task", "action_error"],
)
def test_unqualified_initial_view_never_becomes_a_prompt(fault: str) -> None:
    request = generation_input()
    record = sample_observation(
        request.context.task.identity, request.context.context_id
    )
    if fault == "empty":
        record = record.model_copy(update={"text": ""})
    elif fault == "blank":
        record = record.model_copy(update={"text": "   "})
    elif fault == "loading":
        record = record.model_copy(update={"state": "loading"})
    elif fault == "sequence":
        record = record.model_copy(update={"sequence": 1})
    elif fault == "context":
        record = record.model_copy(update={"context_id": "other"})
    elif fault == "task":
        record = record.model_copy(
            update={"task": record.task.model_copy(update={"task_id": "other"})}
        )
    else:
        record = record.model_copy(update={"last_action_error": "previous failure"})
    with pytest.raises(ValueError):
        prepare_generator(request, ResolvedObservation(record=record, text=record.text))
