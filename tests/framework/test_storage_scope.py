"""Scope declarations: exact versions, complete bindings and root containment."""

from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.storage_scope import StorageScope
from storage_scope_fixtures import scope


@pytest.mark.parametrize("source", [False, True])
def test_scope_exact_roundtrip(source: bool) -> None:
    original = scope(source=source)
    assert StorageScope.model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_root", ""),
        ("workspace_root", "/"),
        ("workspace_root", "/unit/"),
        ("workspace_root", "/unit/../unit"),
        ("workspace_root", "/unit-sibling"),
        ("workspace_root", None),
        ("workspace_root", 3),
        ("claim", {}),
        ("schema_version", "storage-scope/0"),
        ("binding", None),
        ("config", []),
        ("writer", False),
    ],
)
def test_invalid_scope_fields(field: str, value: Any) -> None:
    data = scope().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        StorageScope.model_validate(data)


@pytest.mark.parametrize(
    "path,value",
    [
        (("binding", "storage_id"), "other"),
        (("binding", "storage_config_sha256"), "0" * 64),
        (("binding", "release_id"), "other"),
        (("binding", "owner", "worker_id"), "other"),
        (("execution", "raw_job_id"), "9999"),
        (("run", "owner", "job_id"), "9999"),
        (("run", "plan_ref", "visibility"), "public"),
        (("config", "evidence_root"), "/unit"),
        (("config", "session_root"), "/unit-sibling/state"),
        (("config", "installation", "workspace_root"), "/elsewhere"),
    ],
)
def test_scope_mismatches(path: tuple[str, ...], value: Any) -> None:
    data = scope().model_dump()
    target = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    # Invalid nested configuration can reject before the outer scope check.
    # For structurally valid configurations, rebind digest to test containment.
    with pytest.raises(ValidationError):
        if path[0] == "config":
            from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig

            data["binding"]["storage_config_sha256"] = (
                EvidenceStorageConfig.model_validate(data["config"]).sha256
            )
        StorageScope.model_validate(data)


@pytest.mark.parametrize("case", ["missing", "run", "source", "task"])
def test_source_claim_is_required_and_exact(case: str) -> None:
    data = scope(source=True).model_dump()
    if case == "missing":
        data["claim"] = None
    elif case == "run":
        data["binding"].update(scope="run", source_task_id=None)
    elif case == "source":
        data["binding"]["source_task_id"] = "other"
    else:
        data["claim"]["run"]["submission_key"] = "other"
    with pytest.raises(ValidationError):
        StorageScope.model_validate(data)


def test_empty_and_wrong_type() -> None:
    values: tuple[object, ...] = ({}, None, [], "", 0)
    for value in values:
        with pytest.raises(ValidationError):
            StorageScope.model_validate(value)
