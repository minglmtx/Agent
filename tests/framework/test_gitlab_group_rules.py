"""Exact native group oracle and guard order, without real websites or models."""

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.gitlab_group_creation import evaluate_group as original_group
from lab_generate_skill.site_result_guard import guard_site_result as original_guard
from lab_generate_skill.sites.gitlab.tasks.group_rules import (
    decide_group,
    validate_group_initial,
)
from lab_generate_skill.sites.gitlab.tasks.group_state import GroupNativeState
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from gitlab_group_fixtures import (
    FIXTURE,
    ORIGIN,
    changed,
    selected_spec,
    native_state,
    page,
)

GROUP = cast(Callable[..., dict[str, Any]], original_group)
GUARD = cast(Callable[..., dict[str, Any]], original_guard)


def test_reference_functions_are_exact_original_first_execution_capsule_bytes() -> None:
    root = Path(__file__).resolve().parents[2] / "src/lab_generate_skill"
    for name, sha in {
        "gitlab_group_creation.py": "c65f74f92c3dbf35993689d01b6fee9743d601ef7c4ce05bf3cb4d7d615da03a",
        "site_result_guard.py": "d64a70750918b8034ed2e55c392bfcc803d425ec96d74a40b579c602aec226a2",
        "site_navigation_rules.py": "a3749bb03608565c9e58fb7e0ec42df5ac367aef079193096427e0e2ab26c2ac",
    }.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha


@pytest.mark.parametrize(
    "case",
    [
        "saved",
        "saved-home",
        "nested-allowed",
        "any-path",
        "any-purpose",
        "no-op",
        "wrong-name",
        "wrong-visibility",
        "wrong-company",
        "empty-name",
        "no-owner",
        "wrong-owner",
        "wrong-access",
        "extra-member",
        "old-group",
        "old-member",
        "old-settings",
        "extra-settings",
        "deleted-old",
        "two-groups",
        "login",
        "404",
        "other-origin",
        "500",
        "missing-page",
        "runtime-error",
        "existing-baseline",
        "account-changed",
    ],
)
@pytest.mark.parametrize("projects", [True, False])
def test_original_persisted_group_and_selected_project_guard_match(
    case: str, projects: bool
) -> None:
    before, after = native_state(), native_state(inserted=True)
    terminal: GitlabPageHealth | None = page()
    runtime = case == "runtime-error"
    if case == "saved-home":
        terminal = page(url=ORIGIN)
    elif case == "nested-allowed":
        after = changed(after, "groups", "parent_id", 10)
    elif case == "any-path":
        after = changed(after, "groups", "path", "actor-chosen")
    elif case == "any-purpose":
        after = changed(after, "settings", "jobs_to_be_done", None)
    elif case == "no-op":
        after = before
    elif case == "wrong-name":
        after = changed(after, "groups", "name", "Wrong")
    elif case == "wrong-visibility":
        after = changed(after, "groups", "visibility_level", 20)
    elif case == "wrong-company":
        after = changed(after, "settings", "setup_for_company", False)
    elif case == "empty-name":
        after = changed(after, "groups", "name", "")
    elif case in (
        "no-owner",
        "wrong-owner",
        "wrong-access",
        "extra-member",
        "old-group",
        "old-member",
        "old-settings",
        "extra-settings",
        "deleted-old",
        "two-groups",
    ):
        data = after.model_dump(mode="json")
        if case == "no-owner":
            data["members"].pop()
        elif case == "wrong-owner":
            data["members"][-1]["user_id"] = 2
        elif case == "wrong-access":
            data["members"][-1]["access_level"] = 40
        elif case == "extra-member":
            data["members"].append(
                dict(id=30, source_id=10, user_id=1, access_level=50)
            )
        elif case == "old-group":
            data["groups"][0]["name"] = "changed"
        elif case == "old-member":
            data["members"][0]["access_level"] = 40
        elif case == "old-settings":
            data["settings"][0]["setup_for_company"] = True
        elif case == "extra-settings":
            data["settings"].append(
                dict(namespace_id=30, setup_for_company=True, jobs_to_be_done=None)
            )
        elif case == "deleted-old":
            data["groups"].pop(0)
        elif case == "two-groups":
            data["groups"].append({**data["groups"][-1], "id": 30})
        after = GroupNativeState.model_validate_json(json.dumps(data))
    elif case == "login":
        terminal = page(url=ORIGIN + "users/sign_in", login_page=True, account_id=None)
    elif case == "404":
        terminal = page(http_status=404, error_page=True)
    elif case == "other-origin":
        terminal = page(url="http://127.0.0.1:18081/")
    elif case == "500":
        terminal = page(http_status=500, error_page=True)
    elif case == "missing-page":
        terminal = None
    elif case == "existing-baseline":
        before = native_state(inserted=True)
    elif case == "account-changed":
        data = after.model_dump(mode="json")
        data["user"]["id"] = 2
        after = GroupNativeState.model_validate_json(json.dumps(data))
    old = GROUP(
        json.loads(FIXTURE.read_bytes()),
        None if terminal is None else terminal.model_dump(mode="json"),
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
        site_origin=ORIGIN,
        runtime_error=runtime,
    )
    old = GUARD(old, runtime_error=runtime, selected_records_unchanged=projects)
    current = decide_group(
        selected_spec(),
        before,
        after,
        terminal,
        site_origin=ORIGIN,
        selected_projects_unchanged=projects,
        runtime_error=runtime,
    )
    assert (current.status, current.reward) == (old["status"], old["reward"])
    assert dict(current.checks) == old["checks"]
    assert current.state_change_requires_review == old.get(
        "state_change_requires_review", False
    )


@pytest.mark.parametrize("missing", ["before", "after", "page", "projects", "settings"])
def test_missing_required_evidence_is_unknown_never_failure(missing: str) -> None:
    before, after, terminal = native_state(), native_state(inserted=True), page()
    if missing == "settings":
        data = after.model_dump(mode="json")
        data["settings"] = None
        after = GroupNativeState.model_validate_json(json.dumps(data))
    result = decide_group(
        selected_spec(),
        None if missing == "before" else before,
        None if missing == "after" else after,
        None if missing == "page" else terminal,
        site_origin=ORIGIN,
        selected_projects_unchanged=None if missing == "projects" else True,
    )
    assert result.status == "unknown" and result.reward is None


@pytest.mark.parametrize("bad", [0, 1, "true", [], {}])
def test_wrong_type_guard_cannot_be_truthy_evidence(bad: Any) -> None:
    with pytest.raises(ValueError):
        decide_group(
            selected_spec(),
            native_state(),
            native_state(inserted=True),
            page(),
            site_origin=ORIGIN,
            selected_projects_unchanged=bad,
        )


def test_repeated_readonly_decision_is_identical_and_does_not_mutate_inputs() -> None:
    before, after, terminal, spec = (
        native_state(),
        native_state(inserted=True),
        page(),
        selected_spec(),
    )
    original = before.model_dump_json(), after.model_dump_json(), spec.model_dump_json()
    validate_group_initial(spec, before)
    first = decide_group(
        spec,
        before,
        after,
        terminal,
        site_origin=ORIGIN,
        selected_projects_unchanged=True,
    )
    second = decide_group(
        spec,
        before,
        after,
        terminal,
        site_origin=ORIGIN,
        selected_projects_unchanged=True,
    )
    assert first == second and first.status == "success"
    assert original == (
        before.model_dump_json(),
        after.model_dump_json(),
        spec.model_dump_json(),
    )
