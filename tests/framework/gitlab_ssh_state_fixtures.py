"""Small complete synthetic native facts, never real GitLab acceptance."""

import base64
import json
import struct
from typing import Any
from lab_generate_skill.bootstrap.gitlab_ssh_key import load_ssh_key_inputs
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import (
    SshKeyNativeState,
    AUTH_COLUMNS,
    PROTECTED_TABLES,
)
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from test_gitlab_ssh_key_inputs import FIXTURE, reference, public_task


def selected_spec() -> SshKeySpec:
    raw = FIXTURE.read_bytes()
    return load_ssh_key_inputs(raw, reference(raw), public_task()).private_spec


def native_state(*, inserted: bool = False) -> SshKeyNativeState:
    spec = selected_spec()
    users = [
        dict(
            id=ident,
            username=name,
            admin=False,
            external=False,
            state="active",
            name=name,
            **{column: None for column in AUTH_COLUMNS},
        )
        for ident, name in [(1, "native-user"), (2, "other-user")]
    ]
    users[0]["sign_in_count"] = 0
    users[1]["sign_in_count"] = 0
    wire = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + b"\x01" * 32
    keys = [
        dict(
            id=1,
            user_id=2,
            key="ssh-ed25519 " + base64.b64encode(wire).decode(),
            title="Original unrelated key",
            fingerprint_sha256=None,
            fingerprint=None,
        )
    ]
    if inserted:
        keys.append(
            dict(
                id=2,
                user_id=1,
                key=spec.parameters.public_key,
                title=spec.parameters.title,
                fingerprint_sha256=None,
                fingerprint=None,
            )
        )
    guard: dict[str, Any] = {
        table: dict(rows=1, columns=["id"], key=["id"], sha256="0" * 64)
        for table in PROTECTED_TABLES
    }
    guard["users"].update(rows=len(users), columns=list(users[0]))
    return SshKeyNativeState.model_validate_json(
        json.dumps(
            dict(
                task=spec.task.model_dump(mode="json"),
                account={
                    k: users[0][k]
                    for k in ("id", "username", "admin", "external", "state")
                },
                users=dict(
                    table="users",
                    columns=list(users[0]),
                    rows=users,
                    row_count=len(users),
                    complete=True,
                ),
                keys=dict(
                    table="keys",
                    columns=list(keys[0]),
                    rows=keys,
                    row_count=len(keys),
                    complete=True,
                ),
                guard=guard,
                refs=dict(
                    version="gitlab-all-native-refs-v1",
                    complete=True,
                    repositories={
                        "@hashed/ab/cd/original.git": dict(
                            head="1" * 40,
                            symbolic_head="refs/heads/main",
                            refs={"refs/heads/main": "1" * 40},
                        ),
                        "@hashed/00/00/empty.git": dict(
                            head=None, symbolic_head="refs/heads/main", refs={}
                        ),
                    },
                ),
            )
        )
    )


def page(**updates: Any) -> GitlabPageHealth:
    return GitlabPageHealth(
        **{
            **dict(
                url="http://127.0.0.1:18080/-/profile/keys",
                title="SSH Keys",
                http_status=200,
                status_source="navigation_timing",
                login_page=False,
                error_page=False,
                account_id=1,
            ),
            **updates,
        }
    )


def changed(
    state: SshKeyNativeState, section: str, field: str, value: Any, *, row: int = 0
) -> SshKeyNativeState:
    data = state.model_dump(mode="json")
    if section in ("users", "keys"):
        data[section]["rows"][row][field] = value
    else:
        data[section][field] = value
    return SshKeyNativeState.model_validate_json(json.dumps(data))
