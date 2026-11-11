"""Two exact original contract pins, pure independent semantics, no task dispatch."""

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
from reddit_forum_source_fixtures import CONTRACT, public
from test_reddit_image_inputs import FIXTURE, reference


@pytest.mark.parametrize("case", ["noop", "saved", "wrong-photo", "wrong-title"])
def test_selected_forum_original_goal_matches_current_exact_contract(case: str) -> None:
    raw = CONTRACT.read_bytes()
    ref = reference(raw)
    inputs = load_image_inputs(raw, ref, public())
    initial = reference_data()
    after = (
        initial["capture"]
        if case == "noop"
        else posted_data(0 if case == "wrong-photo" else 1)
    )
    if case != "noop":
        after["added_posts"][0]["title"] = (
            "Other" if case == "wrong-title" else inputs.private_spec.parameters.title
        )
    page = RedditPageHealth(
        url=public().start_url,
        title="Forums",
        http_status=200,
        status_source="navigation_timing",
        login_page=False,
        error_page=False,
    )
    before_model = ImageReference.model_validate_json(json.dumps(initial))
    after_model = NativeCapture.model_validate_json(json.dumps(after))
    issued = inputs.private_spec.parameters.title
    expected = goal_oracle(ref)(
        json.loads(raw),
        initial,
        after,
        page.model_dump(),
        [{"actual_issued_ax": issued}],
        site_origin=public().start_url,
        integrity=preserved(before_model, after_model),
    )
    actual = decide_image(
        inputs.private_spec,
        before_model,
        after_model,
        page,
        issued,
        site_origin=public().start_url,
    )
    assert (actual.status, actual.reward, dict(actual.checks)) == (
        expected["status"],
        expected["reward"],
        expected["checks"],
    )
    assert (
        goal_oracle(ref)(
            json.loads(raw),
            initial,
            after,
            page.model_dump(),
            [{"actual_issued_ax": issued}],
            site_origin=public().start_url,
            integrity=preserved(before_model, after_model),
        )
        == expected
    )


@pytest.mark.parametrize(
    "path", [FIXTURE, CONTRACT], ids=["original-submit", "selected-forums"]
)
@pytest.mark.parametrize("change", ["source", "title", "extra", "empty"])
def test_original_goal_rejects_changed_contract_without_dispatch(
    path: Any, change: str
) -> None:
    raw = path.read_bytes()
    contract = json.loads(raw)
    if change == "source":
        contract["source_task_id"] = "foreign-source"
    elif change == "title":
        contract["public_parameters"]["title"] = "Changed"
    elif change == "extra":
        contract["extra"] = True
    else:
        contract = {}
    with pytest.raises(ValueError, match="Exact selected original contract required"):
        goal_oracle(reference(raw))(
            contract,
            {},
            {},
            {},
            [],
            site_origin="http://127.0.0.1:12001/",
            integrity=True,
        )


@pytest.mark.parametrize("change", ["sha", "size", "schema", "visibility", "media"])
def test_original_goal_rejects_unknown_or_mismatched_reference(change: str) -> None:
    ref = reference(CONTRACT.read_bytes())
    updates_by_case: dict[str, dict[str, object]] = {
        "sha": {"sha256": "f" * 64},
        "size": {"size_bytes": ref.size_bytes + 1},
        "schema": {"content_schema": "foreign/1"},
        "visibility": {"visibility": "public"},
        "media": {"media_type": "text/plain"},
    }
    with pytest.raises(ValueError):
        goal_oracle(ref.model_copy(update=updates_by_case[change]))


@pytest.mark.parametrize("value", [None, {}, [], "reference", 0, True])
def test_original_goal_requires_explicit_typed_reference(value: Any) -> None:
    with pytest.raises(TypeError):
        goal_oracle(value)
