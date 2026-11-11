"""Exact selected contract with small synthetic SQL rows, not site acceptance."""

import hashlib
import json
from pathlib import Path
from typing import Any
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.group_state import GroupNativeState
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth

FIXTURE = Path(__file__).parent / "fixtures/gitlab-group-creation-native.json"
ORIGIN = "http://127.0.0.1:18080/"


def reference(raw: bytes) -> EvidenceRef:
    return EvidenceRef(
        uri="cas:group-native",
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        media_type="application/json",
        content_schema="gitlab-native-contract/1",
        visibility="private",
        producer="test",
    )


def public_task() -> PublicTask:
    native = json.loads(FIXTURE.read_bytes())
    return PublicTask(
        identity=TaskIdentity(
            source_task_id=native["source_task_id"],
            task_id=native["task_id"],
            split="train",
            site="gitlab",
            family="group_creation",
            contract_version=1,
        ),
        goal=native["goal"],
        start_url=ORIGIN + native["start_path"].removeprefix("/"),
        allowed_actions=("click", "fill", "send_msg_to_user"),
    )


def selected_spec() -> GroupSpec:
    raw = FIXTURE.read_bytes()
    return load_group_inputs(raw, reference(raw), public_task())


def native_state(*, inserted: bool = False) -> GroupNativeState:
    groups = [
        dict(
            id=10,
            name="Existing",
            path="existing",
            type="Group",
            visibility_level=20,
            parent_id=None,
        )
    ]
    members = [dict(id=10, source_id=10, user_id=2, access_level=50)]
    settings = [dict(namespace_id=10, setup_for_company=False, jobs_to_be_done=None)]
    if inserted:
        groups.append(
            dict(
                id=20,
                name="Development Team",
                path="development-team",
                type="Group",
                visibility_level=0,
                parent_id=None,
            )
        )
        members.append(dict(id=20, source_id=20, user_id=1, access_level=50))
        settings.append(
            dict(namespace_id=20, setup_for_company=True, jobs_to_be_done=3)
        )
    return GroupNativeState.model_validate_json(
        json.dumps(
            dict(
                task=selected_spec().task.model_dump(mode="json"),
                user=dict(id=1, username="native-user"),
                groups=groups,
                members=members,
                settings=settings,
            )
        )
    )


def changed(
    state: GroupNativeState, section: str, field: str, value: Any, *, row: int = -1
) -> GroupNativeState:
    data = state.model_dump(mode="json")
    data[section][row][field] = value
    return GroupNativeState.model_validate_json(json.dumps(data))


def page(**updates: Any) -> GitlabPageHealth:
    return GitlabPageHealth(
        **{
            **dict(
                url=ORIGIN,
                title="Home",
                http_status=200,
                status_source="navigation_timing",
                login_page=False,
                error_page=False,
                account_id=1,
            ),
            **updates,
        }
    )
