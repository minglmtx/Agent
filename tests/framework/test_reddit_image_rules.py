"""Conditional original goal parity; synthetic native facts, no post effects."""

import json
from typing import Any
import pytest
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.sites.reddit.tasks.image_rules import decide_image
from lab_generate_skill.sites.reddit.evidence_schema import RedditPageHealth
from lab_generate_skill.sites.reddit.image_state import ImageReference
from lab_generate_skill.sites.reddit.native_schema import NativeCapture
from lab_generate_skill.sites.reddit.image_protection import preserved
from reddit_image_state_fixtures import reference_data, posted_data
from reddit_original_image_oracle import goal_oracle
from test_reddit_image_inputs import FIXTURE, reference, public_task


@pytest.mark.parametrize(
    "case",
    [
        "saved",
        "noop",
        "wrong-title",
        "wrong-forum",
        "wrong-photo",
        "not-issued",
        "404",
        "login",
        "error",
        "foreign-origin",
        "503",
        "status-missing",
        "old-comments",
        "two-posts",
        "wrong-account",
    ],
)
def test_conditional_goal_matches_original_capsule(case: str) -> None:
    raw = FIXTURE.read_bytes()
    inputs = load_image_inputs(raw, reference(raw), public_task())
    initial = reference_data()
    after = (
        initial["capture"]
        if case == "noop"
        else posted_data(1 if case == "wrong-photo" else 0)
    )
    if case in ("wrong-title", "wrong-forum", "wrong-account"):
        after["added_posts"][0].update(
            {
                "wrong-title": {"title": "Other"},
                "wrong-forum": {"forum_id": 2},
                "wrong-account": {"user_id": 19},
            }[case]
        )
    if case == "old-comments":
        after["complete13"]["twelve_task_tables"]["comments"]["digest"] = "f" * 32
    if case == "two-posts":
        after["added_posts"].append({**after["added_posts"][0], "id": 4})
    page = RedditPageHealth(
        url=(
            "http://elsewhere/submit"
            if case == "foreign-origin"
            else public_task().start_url
        ),
        title="Submit",
        http_status=(
            None
            if case == "status-missing"
            else 503 if case == "503" else 404 if case == "404" else 200
        ),
        status_source=(
            "unavailable" if case == "status-missing" else "navigation_timing"
        ),
        login_page=case == "login",
        error_page=case == "error",
    )
    issued = (
        "No saved post"
        if case == "not-issued"
        else inputs.private_spec.parameters.title
    )
    before_model = ImageReference.model_validate_json(json.dumps(initial))
    after_model = NativeCapture.model_validate_json(json.dumps(after))
    expected = goal_oracle(reference(raw))(
        json.loads(raw),
        initial,
        after,
        page.model_dump(),
        [{"actual_issued_ax": issued}],
        site_origin=public_task().start_url,
        integrity=preserved(before_model, after_model),
    )
    actual = decide_image(
        inputs.private_spec,
        before_model,
        after_model,
        page,
        issued,
        site_origin=public_task().start_url,
    )
    assert (actual.status, actual.reward) == (expected["status"], expected["reward"])
    if expected["status"] != "unknown":
        assert dict(actual.checks) == expected["checks"]
        assert len(actual.checks) == (2 if case == "noop" else 8)
    else:
        assert all(value is None for _, value in actual.checks)
    assert (
        decide_image(
            inputs.private_spec,
            before_model,
            after_model,
            page,
            issued,
            site_origin=public_task().start_url,
        )
        == actual
    )


@pytest.mark.parametrize("missing", ["reference", "after", "page", "issued", "runtime"])
def test_missing_required_fact_or_runtime_failure_is_unknown(missing: str) -> None:
    raw = FIXTURE.read_bytes()
    inputs = load_image_inputs(raw, reference(raw), public_task())
    initial = ImageReference.model_validate_json(json.dumps(reference_data()))
    after = NativeCapture.model_validate_json(json.dumps(posted_data()))
    page = RedditPageHealth(
        url=public_task().start_url,
        title="Submit",
        http_status=200,
        status_source="navigation_timing",
        login_page=False,
        error_page=False,
    )
    result = decide_image(
        inputs.private_spec,
        None if missing == "reference" else initial,
        None if missing == "after" else after,
        None if missing == "page" else page,
        None if missing == "issued" else inputs.private_spec.parameters.title,
        site_origin=public_task().start_url,
        runtime_error=missing == "runtime",
    )
    assert result.status == "unknown" and result.reward is None


@pytest.mark.parametrize("value", [None, 0, 1, "false", [], {}])
def test_runtime_status_must_be_explicit_bool(value: Any) -> None:
    raw = FIXTURE.read_bytes()
    spec = load_image_inputs(raw, reference(raw), public_task()).private_spec
    with pytest.raises(ValueError):
        decide_image(
            spec,
            None,
            None,
            None,
            None,
            site_origin=public_task().start_url,
            runtime_error=value,
        )
