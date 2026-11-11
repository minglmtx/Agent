"""Original structured response and exact accounting remain distinguishable."""

import json
from typing import Any
import pytest
from lab_generate_skill.adapters.models.teacher_response import OpenRouterTeacherDecoder
from test_actor_protocol import turn


def response() -> dict[str, Any]:
    return dict(
        id="original-provider",
        choices=[
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(turn().skill.model_payload()),
                },
            }
        ],
        usage={
            "cost": 2e-9,
            "prompt_tokens": 100,
            "completion_tokens": 7,
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    )


def test_original_skill_cost_usage_and_missing_token_stats_remain_original() -> None:
    value = response()
    decoder = OpenRouterTeacherDecoder()
    result = decoder.decode(json.dumps(value).encode())
    assert (
        result.skill == turn().skill
        and result.provider_request_id == "original-provider"
    )
    assert result.charge is not None and result.charge.units == 2
    assert (result.input_tokens, result.output_tokens, result.reasoning_tokens) == (
        100,
        7,
        2,
    )
    value["usage"] = {"cost": 2e-9}
    result = decoder.decode(json.dumps(value).encode())
    assert (
        result.input_tokens is result.output_tokens is result.reasoning_tokens is None
    )
    assert result.charge is not None
    value.pop("usage")
    result = decoder.decode(json.dumps(value).encode())
    assert result.charge is None and result.input_tokens is None


@pytest.mark.parametrize(
    "fault",
    [
        "error",
        "missing_id",
        "two_choices",
        "length",
        "tool",
        "role",
        "empty_skill",
        "extra_skill",
        "wrong_skill_type",
        "duplicate_skill",
        "duplicate_response",
        "usage_type",
        "prompt_bool",
        "output_negative",
        "reasoning_bool",
        "reasoning_type",
        "nan",
    ],
)
def test_invalid_empty_partial_duplicate_or_wrong_type_response_is_not_a_good_revision(
    fault: str,
) -> None:
    value = response()
    if fault == "error":
        value["error"] = {"message": "original native error"}
    elif fault == "missing_id":
        value.pop("id")
    elif fault == "two_choices":
        value["choices"] *= 2
    elif fault == "length":
        value["choices"][0]["finish_reason"] = "length"
    elif fault == "tool":
        value["choices"][0]["message"]["tool_calls"] = [{"function": "unknown"}]
    elif fault == "role":
        value["choices"][0]["message"]["role"] = "user"
    elif fault == "empty_skill":
        value["choices"][0]["message"]["content"] = ""
    elif fault == "extra_skill":
        value["choices"][0]["message"]["content"] = json.dumps(
            {**turn().skill.model_payload(), "ignored": True}
        )
    elif fault == "wrong_skill_type":
        value["choices"][0]["message"]["content"] = json.dumps(
            {**turn().skill.model_payload(), "title": 1}
        )
    elif fault == "duplicate_skill":
        value["choices"][0]["message"][
            "content"
        ] = '{"title":"x","title":"y","principle":"Read original evidence.","when_to_apply":"When revising."}'
    elif fault == "duplicate_response":
        raw = json.dumps(value).encode()[:-1] + b',"id":"original-provider"}'
        with pytest.raises(ValueError):
            OpenRouterTeacherDecoder().decode(raw)
        return
    elif fault == "usage_type":
        value["usage"] = []
    elif fault == "prompt_bool":
        value["usage"]["prompt_tokens"] = True
    elif fault == "output_negative":
        value["usage"]["completion_tokens"] = -1
    elif fault == "reasoning_bool":
        value["usage"]["completion_tokens_details"]["reasoning_tokens"] = True
    elif fault == "reasoning_type":
        value["usage"]["completion_tokens_details"] = []
    else:
        value["usage"]["cost"] = float("nan")
    with pytest.raises(ValueError):
        OpenRouterTeacherDecoder().decode(json.dumps(value).encode())
