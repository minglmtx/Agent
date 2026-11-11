"""Original complete-state oracle comparison; explicit unknown-policy differences."""

import hashlib
import json
from typing import Any, Protocol, cast
import pytest
from lab_generate_skill.gitlab_public_bridge_native import evaluate as original_evaluate
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import (
    SshKeyNativeState,
    NativeTable,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_rules import decide_ssh_key, CHECKS
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from gitlab_ssh_state_fixtures import native_state, selected_spec, page, changed
from test_gitlab_ssh_key_inputs import FIXTURE

ORIGIN = "http://127.0.0.1:18080/"


class OriginalOracle(Protocol):
    def __call__(
        self,
        contract: dict[str, Any],
        initial: dict[str, Any],
        final: dict[str, Any],
        captures: list[dict[str, Any]],
        terminal: dict[str, Any],
        *,
        site_origin: str,
    ) -> dict[str, Any]: ...


reference_oracle = cast(OriginalOracle, original_evaluate)


def legacy_table(value: NativeTable) -> dict[str, Any]:
    result = value.model_dump(mode="json")
    result["sha256"] = hashlib.sha256(
        json.dumps(
            result["rows"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    return result


def legacy_state(value: SshKeyNativeState) -> dict[str, Any]:
    return dict(
        version="gitlab-public-bridge-native-candidate-v1",
        kind="native_profile_ssh_key",
        account=value.account.model_dump(mode="json"),
        state=dict(users=legacy_table(value.users), keys=legacy_table(value.keys)),
        guard={
            name: table.model_dump(mode="json") for name, table in value.guard.items()
        },
        refs=value.refs.model_dump(mode="json"),
    )


@pytest.mark.parametrize(
    "case",
    [
        "saved",
        "no_insert",
        "wrong_title",
        "wrong_owner",
        "other_user_auth",
        "own_auth",
        "old_key_changed",
        "profile_changed",
        "fingerprint",
        "existing_initial",
    ],
)
def test_complete_supported_facts_match_original_seven_conditions(case: str) -> None:
    before, after = native_state(), native_state(inserted=True)
    if case == "no_insert":
        after = before
    elif case == "wrong_title":
        after = changed(after, "keys", "title", "Wrong", row=1)
    elif case == "wrong_owner":
        after = changed(after, "keys", "user_id", 2, row=1)
    elif case in ("other_user_auth", "own_auth"):
        after = changed(
            after,
            "users",
            "sign_in_count",
            1,
            row=1 if case == "other_user_auth" else 0,
        )
    elif case == "old_key_changed":
        after = changed(after, "keys", "title", "Changed")
    elif case == "profile_changed":
        after = changed(after, "users", "name", "Wrong")
    elif case == "fingerprint":
        after = changed(after, "keys", "fingerprint", "0" * 32, row=1)
    elif case == "existing_initial":
        before = native_state(inserted=True)
    original = reference_oracle(
        json.loads(FIXTURE.read_bytes()),
        legacy_state(before),
        legacy_state(after),
        [],
        page().model_dump(mode="json"),
        site_origin=ORIGIN,
    )
    current = decide_ssh_key(selected_spec(), before, after, page(), site_origin=ORIGIN)
    assert current.status == original["status"] and current.reward == original["reward"]
    if current.status != "unknown":
        assert current.checks == tuple(original["checks"][name] for name in CHECKS)
    else:
        assert original["checks"] == {}


@pytest.mark.parametrize("case", ["server_error", "missing_actual_account"])
def test_environment_and_missing_account_are_explicit_unknown_policy_changes(
    case: str,
) -> None:
    before, after = native_state(), native_state(inserted=True)
    terminal = (
        page(http_status=503, error_page=True)
        if case == "server_error"
        else page(account_id=None)
    )
    original = reference_oracle(
        json.loads(FIXTURE.read_bytes()),
        legacy_state(before),
        legacy_state(after),
        [],
        terminal.model_dump(mode="json"),
        site_origin=ORIGIN,
    )
    current = decide_ssh_key(
        selected_spec(), before, after, terminal, site_origin=ORIGIN
    )
    assert original["status"] == "failure" and original["reward"] == 0.0
    assert current.status == "unknown" and current.reward is None
    assert current.reason == (
        "TERMINAL_TRANSPORT_UNAVAILABLE"
        if case == "server_error"
        else "CURRENT_ACCOUNT_UNAVAILABLE"
    )


@pytest.mark.parametrize(
    "fault", ["none", "duplicate", "foreign_task", "old_schema", "empty", "nonfinite"]
)
def test_private_native_decoder_has_no_schema_or_scope_upgrade(fault: str) -> None:
    state = native_state()
    raw = state.model_dump_json().encode()
    if fault == "duplicate":
        raw = b'{"schema_version":"gitlab-ssh-key-state/1",' + raw[1:]
    elif fault == "foreign_task":
        data = state.model_dump(mode="json")
        data["task"]["task_id"] = "foreign"
        raw = json.dumps(data).encode()
    elif fault == "old_schema":
        raw = raw.replace(b"gitlab-ssh-key-state/1", b"gitlab-ssh-key-state/0")
    elif fault == "empty":
        raw = b""
    elif fault == "nonfinite":
        raw = raw.replace(b'"sign_in_count":0', b'"sign_in_count":NaN')
    if fault == "none":
        assert load_ssh_key_state(raw, selected_spec()) == state
    else:
        with pytest.raises((ValueError, EvidenceIntegrityError)):
            load_ssh_key_state(raw, selected_spec())
