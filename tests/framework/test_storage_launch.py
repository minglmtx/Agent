"""Strict inline-plan/publication identity, including complete private task match."""

from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.run_plan import RunPlan
from storage_launch_fixtures import selection
from storage_scope_fixtures import scope


@pytest.mark.parametrize("source", [False, True])
def test_launch_roundtrip(source: bool) -> None:
    launch, _ = selection(scope(source=source))
    assert StorageLaunch.model_validate_json(launch.model_dump_json()) == launch


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 0),
        ("revision", 6),
        ("revision", True),
        ("revision", "1"),
        ("revision", 1025),
        ("scope", None),
        ("plan", {}),
        ("plan", []),
        ("deployment", None),
        ("activation", ""),
        ("schema_version", "storage-launch/0"),
    ],
)
def test_invalid_launch(field: str, value: Any) -> None:
    launch, _ = selection()
    data = launch.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        StorageLaunch.model_validate(data)


@pytest.mark.parametrize(
    "case",
    [
        "plan_bytes",
        "plan_run",
        "plan_release",
        "plan_ref_size",
        "release_label",
        "release_ref",
        "claim_task",
        "claim_private",
    ],
)
def test_launch_mismatch(case: str) -> None:
    launch, _ = selection(scope(source=True))
    data = launch.model_dump()
    if case == "plan_bytes":
        data["plan"]["resources"]["operation_timeout_seconds"] += 1
    elif case == "plan_run":
        data["plan"]["run_id"] = "other"
    elif case == "plan_release":
        data["plan"]["release_ref"]["producer"] = "other"
    elif case == "plan_ref_size":
        data["scope"]["run"]["plan_ref"]["size_bytes"] += 1
        data["scope"]["claim"]["run"] = data["scope"]["run"]
    elif case == "release_label":
        data["activation"]["release_id"] = "other"
    elif case == "release_ref":
        data["activation"]["manifest_ref"]["producer"] = "other"
    elif case == "claim_task":
        data["scope"]["claim"]["task"]["registration_id"] = "other"
    else:
        data["scope"]["claim"]["task"]["private_spec_ref"]["producer"] = "other"
    with pytest.raises((ValidationError, ValueError)):
        StorageLaunch.model_validate(data)


def test_rehashed_plan_cannot_drop_original_source() -> None:
    launch, _ = selection(scope(source=True))
    data = launch.model_dump()
    data["plan"]["tasks"][0]["identity"]["source_task_id"] = "other"
    plan = RunPlan.model_validate(data["plan"])
    ref = evidence_reference(
        plan.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="run-plan/3",
            visibility="private",
            producer="run-plans-v1",
        ),
    )
    data["scope"]["run"]["plan_ref"] = ref.model_dump()
    data["scope"]["claim"]["run"] = data["scope"]["run"]
    with pytest.raises(ValidationError, match="absent from the complete plan"):
        StorageLaunch.model_validate(data)
