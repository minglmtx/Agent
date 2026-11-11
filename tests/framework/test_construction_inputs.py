"""Public/private input separation and preserved skill-content semantics."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.construction_inputs import (
    GenerationInput,
    PublicConstructionContext,
    RevisionInput,
)
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.skill_limits import word_count
from lab_generate_skill.domain.task import PublicTask

from test_construction_state import initial, ref, skill


def generation_input() -> GenerationInput:
    return GenerationInput(
        request_id="request",
        context=PublicConstructionContext(
            context_id="context",
            task=PublicTask(
                identity=initial().plan.task.identity,
                goal="Read the public map",
                start_url="https://map.example/",
                allowed_actions=("click", "send_msg_to_user"),
            ),
            initial_observation_ref=ref("observation", "observation/1", "public"),
        ),
        retrieved_skills=tuple(skill(str(index)) for index in range(6)),
        candidate_index=0,
        resample_index=0,
        seed=42,
        temperature=0.7,
    )


def test_public_generation_input_roundtrip_and_three_field_payload() -> None:
    value = generation_input()
    assert GenerationInput.model_validate_json(value.model_dump_json()) == value
    assert set(skill().model_payload()) == {"title", "principle", "when_to_apply"}
    assert (
        "claim_ref" not in value.model_dump_json()
        and "private_spec_ref" not in value.model_dump_json()
    )


@pytest.mark.parametrize(
    "field", ["claim_ref", "private_spec_ref", "baseline_ref", "dependencies"]
)
def test_private_fields_are_not_generator_input(field: str) -> None:
    values = generation_input().model_dump(mode="python")
    values[field] = ref("secret")
    with pytest.raises(ValidationError):
        GenerationInput.model_validate(values)


def test_private_observation_and_wrong_retrieval_count_rejected() -> None:
    values = generation_input().model_dump(mode="python")
    values["context"]["initial_observation_ref"] = ref("private")
    with pytest.raises(ValidationError):
        GenerationInput.model_validate(values)
    values = generation_input().model_dump(mode="python")
    values["retrieved_skills"] = ()
    with pytest.raises(ValidationError):
        GenerationInput.model_validate(values)


@pytest.mark.parametrize(
    "visibility,schema",
    [
        ("private", "teacher-input/1"),
        ("public", "teacher-input/1"),
        ("teacher", "raw-trace/1"),
    ],
)
def test_teacher_only_consumes_declared_projection(
    visibility: str, schema: str
) -> None:
    with pytest.raises(ValidationError):
        RevisionInput(
            request_id="teacher",
            teacher_round=1,
            seed=42,
            projection_ref=ref("data", schema, visibility),
        )


def test_teacher_input_roundtrip() -> None:
    value = RevisionInput(
        request_id="teacher",
        teacher_round=1,
        seed=42,
        projection_ref=ref("data", "teacher-input/1", "teacher"),
    )
    assert RevisionInput.model_validate_json(value.model_dump_json()) == value


def test_skill_stripping_and_existing_content_digest() -> None:
    value = CompactSkill(
        title="  Map café  ",
        principle=" Read the map. ",
        when_to_apply=" A visible map. ",
    )
    payload = {
        "title": "Map café",
        "principle": "Read the map.",
        "when_to_apply": "A visible map.",
    }
    assert value.model_payload() == payload
    assert (
        value.content_digest
        == hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
    )
    assert CompactSkill.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", " "),
        ("title", None),
        ("principle", []),
        ("when_to_apply", 1),
        ("unknown", "secret"),
        ("title", " ".join(["word"] * 13)),
        ("principle", " ".join(["word"] * 201)),
        ("when_to_apply", " ".join(["word"] * 71)),
        ("principle", "- unnumbered step"),
        ("principle", "2. wrong first"),
        ("principle", "1. first\n3. missing second"),
        ("principle", "Intro\n1. step"),
        ("principle", "1. first\n2."),
        ("principle", "\n".join(f"{index}. step" for index in range(1, 8))),
    ],
)
def test_invalid_skill_content(field: str, value: object) -> None:
    fields = skill().model_dump(mode="python")
    fields[field] = value
    with pytest.raises(ValidationError):
        CompactSkill.model_validate(fields)


def test_skill_exact_total_limit_and_numbered_step_semantics() -> None:
    value = CompactSkill(
        title=" ".join(["title"] * 12),
        principle=" ".join(["body"] * 138),
        when_to_apply=" ".join(["when"] * 70),
    )
    assert sum(word_count(field) for field in value.model_payload().values()) == 220
    with pytest.raises(ValidationError):
        CompactSkill(
            title=value.title,
            principle=value.principle + " extra",
            when_to_apply=value.when_to_apply,
        )
    assert word_count("1. Click saved-items. 2. Don't alter 29.99.") == 6
    CompactSkill(
        title="Steps",
        principle="1. Read carefully. 2. Save and verify.",
        when_to_apply="When needed.",
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("saved-items", 1),
        ("Don't", 1),
        ("29.99", 2),
        ("1. Click.\n2. Save.", 2),
        ("Click saved-items. Don't alter 29.99.", 6),
    ],
)
def test_word_count_variants_preserve_original_policy(text: str, expected: int) -> None:
    assert word_count(text) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_index", True),
        ("candidate_index", 4),
        ("resample_index", 5),
        ("seed", -1),
        ("seed", "42"),
        ("temperature", float("nan")),
        ("temperature", float("inf")),
        ("temperature", -0.1),
    ],
)
def test_generation_input_rejects_invalid_sampling(field: str, value: object) -> None:
    fields = generation_input().model_dump(mode="python")
    fields[field] = value
    with pytest.raises(ValidationError):
        GenerationInput.model_validate(fields)
