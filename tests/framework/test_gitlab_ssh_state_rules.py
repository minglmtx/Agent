"""Full native schema/negative/unknown cases for the selected supplied key."""

import base64
import hashlib
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import SshKeyNativeState
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from lab_generate_skill.sites.gitlab.tasks.ssh_key_rules import decide_ssh_key, CHECKS
from gitlab_ssh_state_fixtures import selected_spec, native_state, page, changed

ORIGIN = "http://127.0.0.1:18080/"


def test_saved_native_key_and_all_protected_state_are_required_and_repeatable() -> None:
    before, after = native_state(), native_state(inserted=True)
    result = decide_ssh_key(selected_spec(), before, after, page(), site_origin=ORIGIN)
    assert result.status == "success" and result.reward == 1
    assert result.checks == (True,) * len(CHECKS)
    assert (
        decide_ssh_key(selected_spec(), before, after, page(), site_origin=ORIGIN)
        == result
    )
    assert before.keys.row_count == 1 and after.keys.row_count == 2


@pytest.mark.parametrize(
    "field", ["sign_in_count", "current_sign_in_at", "last_activity_on", "updated_at"]
)
def test_only_bound_account_auth_metadata_may_change(field: str) -> None:
    before, after = native_state(), native_state(inserted=True)
    value = 1 if field == "sign_in_count" else "2026-01-01T00:00:00Z"
    own = changed(after, "users", field, value)
    assert (
        decide_ssh_key(selected_spec(), before, own, page(), site_origin=ORIGIN).status
        == "success"
    )
    other = changed(after, "users", field, value, row=1)
    result = decide_ssh_key(selected_spec(), before, other, page(), site_origin=ORIGIN)
    assert result.status == "failure" and result.checks[0] is False


@pytest.mark.parametrize(
    "fault",
    [
        "no_insert",
        "wrong_title",
        "wrong_key",
        "wrong_owner",
        "changed_existing",
        "extra_key",
        "deleted_existing",
        "changed_user",
        "guard",
        "refs",
        "wrong_page_account",
        "offsite",
        "login",
        "404",
    ],
)
def test_complete_negative_facts_are_valid_failure(fault: str) -> None:
    before, after = native_state(), native_state(inserted=True)
    terminal = page()
    if fault == "no_insert":
        after = before
    elif fault in ("wrong_title", "wrong_key", "wrong_owner"):
        field, value = {
            "wrong_title": ("title", "Wrong"),
            "wrong_key": ("key", before.keys.rows[0]["key"]),
            "wrong_owner": ("user_id", 2),
        }[fault]
        after = changed(after, "keys", field, value, row=1)
    elif fault == "changed_existing":
        after = changed(after, "keys", "title", "Changed old key")
    elif fault == "changed_user":
        after = changed(after, "users", "name", "Unauthorized profile rename")
    elif fault in ("extra_key", "deleted_existing", "guard", "refs"):
        data = after.model_dump(mode="json")
        if fault == "extra_key":
            data["keys"]["rows"].append({**data["keys"]["rows"][-1], "id": 3})
            data["keys"]["row_count"] += 1
        elif fault == "deleted_existing":
            data["keys"]["rows"].pop(0)
            data["keys"]["row_count"] -= 1
        elif fault == "guard":
            data["guard"]["projects"]["sha256"] = "f" * 64
        else:
            data["refs"]["repositories"]["@hashed/ab/cd/original.git"]["head"] = (
                "2" * 40
            )
        after = SshKeyNativeState.model_validate_json(json.dumps(data))
    elif fault == "wrong_page_account":
        terminal = terminal.model_copy(update={"account_id": 2})
    elif fault == "offsite":
        terminal = terminal.model_copy(
            update={"url": "https://outside.invalid/profile"}
        )
    elif fault == "login":
        terminal = terminal.model_copy(update={"login_page": True, "account_id": None})
    else:
        terminal = terminal.model_copy(update={"http_status": 404, "error_page": True})
    result = decide_ssh_key(
        selected_spec(), before, after, terminal, site_origin=ORIGIN
    )
    assert result.status == "failure" and result.reward == 0 and not all(result.checks)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_before",
        "missing_after",
        "missing_page",
        "missing_http",
        "http500",
        "missing_account",
        "scope",
        "existing_supplied_key",
        "bad_key",
        "runtime",
        "origin",
    ],
)
def test_missing_or_environment_facts_stay_unknown(fault: str) -> None:
    before: SshKeyNativeState | None = native_state()
    after: SshKeyNativeState | None = native_state(inserted=True)
    terminal: GitlabPageHealth | None = page()
    if fault == "missing_before":
        before = None
    elif fault == "missing_after":
        after = None
    elif fault == "missing_page":
        terminal = None
    elif fault == "missing_http":
        assert terminal is not None
        terminal = terminal.model_copy(
            update={"http_status": None, "status_source": "unavailable"}
        )
    elif fault == "http500":
        assert terminal is not None
        terminal = terminal.model_copy(update={"http_status": 503, "error_page": True})
    elif fault == "missing_account":
        assert terminal is not None
        terminal = terminal.model_copy(update={"account_id": None})
    elif fault == "scope":
        assert after is not None
        after = after.model_copy(
            update={"task": after.task.model_copy(update={"task_id": "other"})}
        )
    elif fault == "existing_supplied_key":
        before = native_state(inserted=True)
    elif fault == "bad_key":
        assert after is not None
        after = changed(after, "keys", "key", "ssh-ed25519 invalid", row=1)
    result = decide_ssh_key(
        selected_spec(),
        before,
        after,
        terminal,
        site_origin="missing" if fault == "origin" else ORIGIN,
        runtime_error=fault == "runtime",
    )
    assert (
        result.status == "unknown"
        and result.reward is None
        and result.checks == (None,) * len(CHECKS)
    )


@pytest.mark.parametrize(
    "form", ["display", "bare", "bytea", "md5_colon", "md5_hex", "bad_sha", "bad_md5"]
)
def test_native_fingerprint_encodings_match_full_wire(form: str) -> None:
    before, after = native_state(), native_state(inserted=True)
    wire = base64.b64decode(selected_spec().parameters.public_key.split()[1])
    sha = hashlib.sha256(wire).digest()
    display = base64.b64encode(sha).decode().rstrip("=")
    md5 = hashlib.md5(wire).hexdigest()
    field, value = {
        "display": ("fingerprint_sha256", "SHA256:" + display),
        "bare": ("fingerprint_sha256", display),
        "bytea": ("fingerprint_sha256", "\\x" + sha.hex()),
        "md5_colon": (
            "fingerprint",
            ":".join(md5[i : i + 2] for i in range(0, len(md5), 2)),
        ),
        "md5_hex": ("fingerprint", md5),
        "bad_sha": ("fingerprint_sha256", "\\x" + "0" * 64),
        "bad_md5": ("fingerprint", "0" * 32),
    }[form]
    after = changed(after, "keys", field, value, row=1)
    result = decide_ssh_key(selected_spec(), before, after, page(), site_origin=ORIGIN)
    assert result.status == ("failure" if form.startswith("bad") else "success")


@pytest.mark.parametrize(
    "fault",
    [
        "missing_guard",
        "incomplete",
        "bool_complete",
        "schema",
        "row_count",
        "missing_column",
        "missing_value",
        "bool_id",
        "duplicate_id",
        "order",
        "nan",
        "account_admin",
        "user_flag",
        "keys_type",
        "guard_columns",
        "empty_refs",
        "refs_complete",
        "repository_alias",
        "bad_oid",
        "bad_ref",
        "foreign_task",
    ],
)
def test_malformed_native_capture_is_rejected(fault: str) -> None:
    data = native_state().model_dump(mode="json")
    if fault == "missing_guard":
        del data["guard"]["members"]
    elif fault in ("incomplete", "bool_complete"):
        data["users"]["complete"] = False if fault == "incomplete" else 1
    elif fault == "schema":
        data["schema_version"] = "gitlab-ssh-key-state/0"
    elif fault == "row_count":
        data["keys"]["row_count"] = 2
    elif fault == "missing_column":
        data["users"]["columns"].remove("updated_at")
    elif fault == "missing_value":
        del data["users"]["rows"][0]["name"]
    elif fault == "bool_id":
        data["keys"]["rows"][0]["id"] = True
    elif fault == "duplicate_id":
        data["users"]["rows"][1]["id"] = 1
    elif fault == "order":
        data["users"]["rows"].reverse()
    elif fault == "nan":
        data["users"]["rows"][0]["name"] = float("nan")
    elif fault == "account_admin":
        data["account"]["admin"] = 0
    elif fault == "user_flag":
        data["users"]["rows"][0]["admin"] = 0
    elif fault == "keys_type":
        data["keys"]["rows"][0]["user_id"] = True
    elif fault == "guard_columns":
        data["guard"]["users"]["columns"].remove("name")
    elif fault == "empty_refs":
        data["refs"]["repositories"] = {}
    elif fault == "refs_complete":
        data["refs"]["complete"] = 1
    elif fault == "repository_alias":
        data["refs"]["repositories"]["../foreign.git"] = data["refs"][
            "repositories"
        ].pop("@hashed/00/00/empty.git")
    elif fault == "bad_oid":
        data["refs"]["repositories"]["@hashed/ab/cd/original.git"]["head"] = "1" * 41
    elif fault == "bad_ref":
        data["refs"]["repositories"]["@hashed/ab/cd/original.git"]["refs"] = {
            "refs/heads/a..b": "1" * 40
        }
    else:
        data["task"]["site"] = "shopping"
    with pytest.raises(ValidationError):
        SshKeyNativeState.model_validate_json(json.dumps(data))
