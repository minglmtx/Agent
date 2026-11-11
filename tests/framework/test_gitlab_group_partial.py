"""Partial facts retain their original boundary and cannot qualify a full capture."""

import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import pytest
from lab_generate_skill.sites.gitlab.tasks.group_partial import GroupPartialCapture
from gitlab_group_lifecycle_fixtures import case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "change,value",
    [
        ("schema_version", "gitlab-group-capture-payload/1"),
        ("failed_stage", "unknown"),
        ("failed_stage", None),
        ("group_reply_base64", 1),
        ("group_reply_base64", "!"),
        ("project_copy_base64", "eA=="),
        ("project_query", "SELECT true"),
        ("qualified", True),
        ("extra", 1),
        ("parent", "foreign"),
        ("owner", "foreign"),
        ("mode", "execute"),
    ],
)
def test_illegal_partial_identity_or_fake_complete_facts_rejected(
    node_path: Path, change: str, value: Any
) -> None:
    c = case(node_path)
    original = GroupPartialCapture(
        request=c.request,
        retention_operation=c.request.operation.cleanup(
            "diagnostic", now=datetime.now(timezone.utc), seconds=30
        ),
        failed_stage="groups",
        group_reply_base64=None,
        project_copy_base64=None,
    )
    data = original.model_dump(mode="json")
    if change in ("parent", "owner", "mode"):
        key = {"parent": "parent_operation_id", "owner": "owner_id", "mode": "mode"}[
            change
        ]
        data["retention_operation"][key] = value
    else:
        data[change] = value
    with pytest.raises(ValueError):
        GroupPartialCapture.model_validate_json(json.dumps(data))
    assert not c.sql.calls and not c.artifacts.calls
    c.task.instance.stop(guard())
