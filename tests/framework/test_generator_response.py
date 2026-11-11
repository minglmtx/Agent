"""Retain formatting tolerance, reject ambiguous or invalid saved model output."""

import json
from typing import cast
import pytest
from lab_generate_skill.generator.response import (
    parse_generated_skill,
    parameter_object,
)
from test_construction_state import skill


@pytest.mark.parametrize(
    "prefix,suffix",
    [
        ("", ""),
        ("```json\n", "\n```"),
        ("<think>plan</think>\n", ""),
        ("not json { broken\n", " trailing text"),
    ],
)
def test_existing_first_json_skill_tolerance(prefix: str, suffix: str) -> None:
    expected = skill("one")
    assert (
        parse_generated_skill(
            prefix + json.dumps(expected.model_payload()) + suffix, "stop"
        )
        == expected
    )


@pytest.mark.parametrize("reason", ["length", "content_filter", "error", "unknown", ""])
def test_abnormal_finish_cannot_return_a_candidate(reason: str) -> None:
    with pytest.raises(ValueError):
        parse_generated_skill(json.dumps(skill().model_payload()), reason)


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "  ",
        "not json",
        "{}",
        '{"title":"x","title":"y","principle":"p","when_to_apply":"w"}',
        '{"title":NaN,"principle":"p","when_to_apply":"w"}',
        '{"title":3,"principle":"p","when_to_apply":"w"}',
        '{"title":"","principle":"p","when_to_apply":"w"}',
        '{"title":"x","principle":"p","when_to_apply":"w","schema_version":"compact-skill/1"}',
    ],
)
def test_empty_illegal_or_ambiguous_payload_rejected(payload: str) -> None:
    with pytest.raises(ValueError):
        parse_generated_skill(payload, "stop")


@pytest.mark.parametrize("value", [None, {}, [], 1, True])
def test_wrong_text_type(value: object) -> None:
    with pytest.raises(TypeError):
        parse_generated_skill(cast(str, value), "stop")


def test_existing_skill_hard_limits_not_relaxed() -> None:
    payload = skill().model_payload()
    payload["title"] = "word " * 13
    with pytest.raises(ValueError):
        parse_generated_skill(json.dumps(payload), "stop")


@pytest.mark.parametrize(
    "raw", [b"[]", b"", b'{"seed":1,"seed":2}', b'{"temperature":NaN}']
)
def test_sampling_json_rejects_ambiguity(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parameter_object(raw)
