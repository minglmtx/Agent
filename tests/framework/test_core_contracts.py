"""Reject boundary coercion, private-input leakage and invalid scored results."""

import json

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.evaluation import CheckResult, Evaluation
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask, TaskBinding


def identity() -> TaskIdentity:
    return TaskIdentity(
        source_task_id="source-1",
        task_id="derived-1",
        split="train",
        site="map",
        family="export",
        contract_version=1,
    )


def reference(
    visibility: str = "private", content_schema: str = "native-facts/1"
) -> EvidenceRef:
    return EvidenceRef.model_validate(
        {
            "uri": "cas://sha256/" + "a" * 64,
            "sha256": "a" * 64,
            "size_bytes": 1,
            "media_type": "application/json",
            "content_schema": content_schema,
            "visibility": visibility,
            "producer": "collector-1",
        }
    )


def test_identity_round_trip_preserves_lineage() -> None:
    task = identity()
    assert TaskIdentity.model_validate_json(task.model_dump_json()) == task
    assert task.task_id != task.source_task_id


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract_version", True),
        ("contract_version", "1"),
        ("contract_version", 0),
        ("split", "validation"),
        ("site", "unknown"),
        ("family", " "),
        ("schema_version", "task-identity/2"),
        ("private_answer", "secret"),
    ],
)
def test_identity_rejects_coercion_and_unversioned_extras(
    field: str, value: object
) -> None:
    data = identity().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        TaskIdentity.model_validate(data)


def test_public_task_round_trip_and_immutable_actions() -> None:
    task = PublicTask(
        identity=identity(),
        goal="Export the visible map",
        start_url="https://map.example/",
        allowed_actions=("click", "stop"),
    )
    restored = PublicTask.model_validate_json(task.model_dump_json())
    assert restored == task
    assert isinstance(restored.allowed_actions, tuple)
    with pytest.raises(ValidationError):
        setattr(task, "goal", "Changed task")


@pytest.mark.parametrize(
    "extra", ["private_spec_ref", "private_answer", "baseline_ref"]
)
def test_private_fields_cannot_enter_public_task(extra: str) -> None:
    payload = {
        "identity": identity().model_dump(),
        "goal": "Read map",
        "start_url": "https://map.example/",
        "allowed_actions": ["click"],
        extra: "hidden",
    }
    with pytest.raises(ValidationError):
        PublicTask.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "url",
    [
        "file:///secret",
        "https://user:password@map.example/",
        "https:///no-host",
        "https://map.example/raw space",
    ],
)
def test_public_start_rejects_local_or_credentialed_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        PublicTask(
            identity=identity(),
            goal="Read map",
            start_url=url,
            allowed_actions=("click",),
        )


def test_binding_preserves_private_views_without_public_serialization() -> None:
    binding = TaskBinding(
        identity=identity(),
        registration_id="map.export.v1",
        public_task_ref=reference("public", "public-task/1"),
        private_spec_ref=reference(),
        baseline_ref=reference(),
    )
    assert TaskBinding.model_validate_json(binding.model_dump_json()) == binding
    broken = binding.model_dump()
    broken["public_task_ref"] = reference().model_dump()
    with pytest.raises(ValidationError):
        TaskBinding.model_validate(broken)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "A" * 64),
        ("size_bytes", True),
        ("size_bytes", -1),
        ("uri", "relative/path"),
        ("uri", "https://key:secret@example.org/data"),
    ],
)
def test_reference_rejects_ambiguous_content_identity(
    field: str, value: object
) -> None:
    data = reference().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(data)


def judgment_payload(status: str, reward: object, check: str) -> dict[str, object]:
    return {
        "identity": identity().model_dump(),
        "attempt_id": "attempt-1",
        "contract_ref": reference().model_dump(),
        "evaluator_id": "map.export",
        "evaluator_version": "1",
        "status": status,
        "reward": reward,
        "checks": (
            {
                "name": "artifact",
                "status": check,
                "reason_code": "CHECKED",
                "evidence": (reference().model_dump(),),
            },
        ),
        "reason_code": "CHECKED",
    }


@pytest.mark.parametrize(
    "status,reward,check",
    [("success", 1, "pass"), ("failure", 0, "fail"), ("unknown", None, "unknown")],
)
def test_evaluation_round_trip_preserves_three_valued_reward(
    status: str, reward: object, check: str
) -> None:
    result = Evaluation.model_validate(judgment_payload(status, reward, check))
    assert Evaluation.model_validate_json(result.model_dump_json()) == result
    assert result.reward == reward


@pytest.mark.parametrize(
    "status,reward,check",
    [
        ("success", True, "pass"),
        ("failure", False, "fail"),
        ("success", 1.0, "pass"),
        ("unknown", 0, "unknown"),
        ("success", 0, "pass"),
        ("failure", 1, "fail"),
        ("success", 1, "unknown"),
        ("failure", 0, "unknown"),
        ("success", 1, "fail"),
        ("failure", 0, "pass"),
    ],
)
def test_invalid_reward_or_incomplete_checks_are_not_scored(
    status: str, reward: object, check: str
) -> None:
    with pytest.raises(ValidationError):
        Evaluation.model_validate(judgment_payload(status, reward, check))


def test_scored_result_needs_attributable_checks() -> None:
    data = judgment_payload("success", 1, "pass")
    data["checks"] = (
        CheckResult(name="artifact", status="pass", reason_code="UNSUPPORTED"),
    )
    with pytest.raises(ValidationError):
        Evaluation.model_validate(data)
    data["checks"] = ()
    with pytest.raises(ValidationError):
        Evaluation.model_validate(data)


def test_evidence_requirements_reject_duplicate_subscriptions() -> None:
    with pytest.raises(ValidationError):
        EvidenceRequirements(events=("download", "download"))
