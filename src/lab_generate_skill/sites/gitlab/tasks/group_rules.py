"""Original group-creation conditions and selected-project guard priority."""

from urllib.parse import urlsplit
from ..evidence_schema import GitlabPageHealth
from ..evidence_schema import GroupOutcome
from .group_spec import GroupSpec
from .group_state import GroupNativeState


def validate_group_initial(spec: GroupSpec, state: GroupNativeState) -> None:
    spec = GroupSpec.model_validate(spec)
    state = GroupNativeState.model_validate(state)
    if state.task != spec.task:
        raise ValueError("Native group state changed original task")
    req = spec.requirements
    if req.name is not None and any(row.name == req.name for row in state.groups):
        raise ValueError("Named group already exists")
    if req.path is not None and any(row.path == req.path for row in state.groups):
        raise ValueError("Requested group path already exists")
    if (req.settings is not None) != (state.settings is not None):
        raise ValueError("Native group settings coverage differs from contract")


def decide_group(
    spec: GroupSpec,
    before: GroupNativeState | None,
    after: GroupNativeState | None,
    page: GitlabPageHealth | None,
    *,
    site_origin: str,
    selected_projects_unchanged: bool | None,
    runtime_error: bool = False,
) -> GroupOutcome:
    spec = GroupSpec.model_validate(spec)
    if type(runtime_error) is not bool or (
        selected_projects_unchanged is not None
        and type(selected_projects_unchanged) is not bool
    ):
        raise ValueError(
            "Explicit runtime and selected-project evidence flags required"
        )

    def unknown(reason: str) -> GroupOutcome:
        if selected_projects_unchanged is False and not runtime_error:
            return GroupOutcome("unknown", None, (), "PROTECTED_PROJECTS_CHANGED", True)
        return GroupOutcome("unknown", None, (), reason)

    if runtime_error or before is None or after is None:
        return unknown("INCOMPLETE_NATIVE_STATE")
    before, after = GroupNativeState.model_validate(
        before
    ), GroupNativeState.model_validate(after)
    try:
        validate_group_initial(spec, before)
    except ValueError:
        return unknown("INVALID_GROUP_BASELINE")
    if after.task != spec.task or before.user != after.user:
        return unknown("NATIVE_TASK_OR_ACCOUNT_CHANGED")
    if (spec.requirements.settings is not None) != (after.settings is not None):
        return unknown("INCOMPLETE_GROUP_SETTINGS")
    if page is None:
        return unknown("MISSING_TERMINAL_PAGE")
    page = GitlabPageHealth.model_validate(page)
    if page.http_status is None or not 200 <= page.http_status < 500:
        return unknown("TERMINAL_TRANSPORT_UNAVAILABLE")
    try:
        origin, actual = urlsplit(site_origin), urlsplit(page.url)
        if (origin.scheme, origin.hostname) != ("http", "127.0.0.1") or (
            origin.port is None
            or origin.username is not None
            or origin.password is not None
            or origin.path not in ("", "/")
            or origin.query
            or origin.fragment
        ):
            return unknown("INVALID_SITE_ORIGIN")
    except ValueError:
        return unknown("INVALID_SITE_ORIGIN")
    if selected_projects_unchanged is None:
        return unknown("MISSING_SELECTED_PROJECT_EVIDENCE")
    old, current = {r.id: r for r in before.groups}, {r.id: r for r in after.groups}
    old_members, current_members = {r.id: r for r in before.members}, {
        r.id: r for r in after.members
    }
    added = [r for r in after.groups if r.id not in old]
    added_members = [r for r in after.members if r.id not in old_members]
    checks = {
        "page_valid": (actual.scheme, actual.netloc) == (origin.scheme, origin.netloc)
        and 200 <= page.http_status < 300
        and not page.login_page
        and not page.error_page,
        "existing_groups_unchanged": all(
            current.get(k) == row for k, row in old.items()
        ),
        "existing_memberships_unchanged": all(
            current_members.get(k) == row for k, row in old_members.items()
        ),
        "one_group_saved": len(added) == 1,
    }
    req = spec.requirements
    settings = {r.namespace_id: r for r in (after.settings or ())}
    if req.settings is not None:
        prior = {r.namespace_id: r for r in (before.settings or ())}
        checks["existing_group_settings_unchanged"] = all(
            settings.get(k) == row for k, row in prior.items()
        )
        checks["no_unrelated_group_settings_added"] = set(settings) - set(prior) <= {
            r.id for r in added
        }
    if len(added) == 1:
        group = added[0]
        checks.update(
            requested_name=req.name is None or group.name == req.name,
            requested_visibility=req.visibility_level is None
            or group.visibility_level == req.visibility_level,
            requested_hierarchy=not req.top_level or group.parent_id is None,
            native_fields_saved=bool(group.name.strip()) and bool(group.path.strip()),
            owned_by_current_account=any(
                r.source_id == group.id
                and r.user_id == before.user.id
                and r.access_level == 50
                for r in added_members
            ),
            no_unrelated_membership_added=all(
                r.source_id == group.id for r in added_members
            ),
        )
        if req.path is not None:
            checks["requested_path"] = group.path == req.path
        if req.settings is not None:
            saved = settings.get(group.id)
            for key, value in req.settings.model_dump(exclude_unset=True).items():
                checks["requested_" + key] = (
                    saved is not None and getattr(saved, key) == value
                )
    passed = all(checks.values())
    facts = tuple(checks.items())
    if not selected_projects_unchanged:
        if passed:
            return GroupOutcome(
                "unknown", None, facts, "PROTECTED_PROJECTS_CHANGED", True
            )
        return GroupOutcome(
            "failure", 0, facts, "GOAL_FAILED_AND_PROTECTED_PROJECTS_CHANGED", True
        )
    return GroupOutcome("success" if passed else "failure", int(passed), facts, None)
