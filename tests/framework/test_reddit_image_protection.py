"""Original native guard parity: full evidence versus malformed/partial facts."""

from copy import deepcopy
import json
from typing import Any
import pytest
from lab_generate_skill.sites.reddit.native_schema import (
    NativeCapture,
    SubmissionDigest,
)
from lab_generate_skill.sites.reddit.image_state import ImageReference
from lab_generate_skill.sites.reddit.image_protection import preserved
from reddit_image_state_fixtures import reference_data, posted_data, STAMP
from reddit_original_image_oracle import oracle


def current(initial: dict[str, Any], terminal: dict[str, Any]) -> bool:
    return preserved(
        ImageReference.model_validate_json(json.dumps(initial)),
        NativeCapture.model_validate_json(json.dumps(terminal)),
    )


@pytest.mark.parametrize(
    "case",
    [
        "no-op",
        "positive",
        "wrong-photo",
        "wrong-forum",
        "wrong-title",
        "empty-body-null",
        "native-thumbnail",
    ],
)
def test_complete_native_scope_is_independent_from_goal_meaning(case: str) -> None:
    before = reference_data()
    after = (
        deepcopy(before["capture"])
        if case == "no-op"
        else posted_data(1 if case == "wrong-photo" else 0)
    )
    if case == "wrong-forum":
        after["added_posts"][0]["forum_id"] = 2
    elif case == "wrong-title":
        after["added_posts"][0]["title"] = "Different native title"
    elif case == "empty-body-null":
        after["added_posts"][0]["body"] = None
    elif case == "native-thumbnail":
        image = after["attached_image"]
        name = "media/cache/submission_thumbnail_1x/" + image["file_name"]
        after["native_media"]["directories"] = sorted(
            [
                "submission_images",
                "media",
                "media/cache",
                "media/cache/submission_thumbnail_1x",
            ]
        )
        after["native_media"]["files"][name] = dict(
            bytes=101, sha256="d" * 64, format="JPEG", dimensions=[70, 70]
        )
    assert current(before, after) is True
    assert oracle()(before, after) is True


@pytest.mark.parametrize(
    "case",
    [
        "old-comments",
        "old-users",
        "old-posts",
        "old-aux",
        "missing-new-post",
        "two-new-posts",
        "old-id",
        "wrong-account",
        "unknown-forum",
        "nonempty-body",
        "external-url",
        "wrong-media-type",
        "hidden-post",
        "bool-count",
        "edited",
        "net-score",
        "unpaired-times",
        "naive-time",
        "bad-ip",
        "wrong-vote",
        "two-votes",
        "wrong-vote-id",
        "wrong-vote-time",
        "wrong-excluded-post",
        "wrong-excluded-image",
        "wrong-image-association",
        "wrong-original-bytes",
        "wrong-original-dimensions",
        "unrelated-file",
        "wrong-thumbnail",
        "extra-directory",
    ],
)
def test_unscoped_or_partial_native_side_effects_never_pass(case: str) -> None:
    before = reference_data()
    after = posted_data()
    post = after["added_posts"][0]
    if case == "old-comments":
        after["complete13"]["twelve_task_tables"]["comments"]["digest"] = "e" * 32
    elif case == "old-users":
        after["complete13"]["twelve_task_tables"]["users"]["digest"] = "e" * 32
    elif case == "old-posts":
        after["all_original_submissions"]["sha256"] = "e" * 64
    elif case == "old-aux":
        after["auxiliary"]["auxiliary"]["notifications"]["digest"] = "e" * 32
    elif case == "missing-new-post":
        after["added_posts"] = []
    elif case == "two-new-posts":
        after["added_posts"].append(deepcopy(post))
    elif case == "old-id":
        post["id"] = 2
    elif case == "wrong-account":
        post["user_id"] = 18
    elif case == "unknown-forum":
        post["forum_id"] = 99
    elif case == "nonempty-body":
        post["body"] = "unapproved body"
    elif case == "external-url":
        post["url"] = "https://outside.invalid/"
    elif case == "wrong-media-type":
        post["media_type"] = "url"
    elif case == "hidden-post":
        post["visibility"] = "hidden"
    elif case == "bool-count":
        post["comment_count"] = False
    elif case == "edited":
        post["edited_at"] = STAMP
    elif case == "net-score":
        post["net_score"] = 0
    elif case == "unpaired-times":
        post["last_active"] = "2026-10-29T12:00:01+00:00"
    elif case == "naive-time":
        post["timestamp"] = post["last_active"] = "2026-10-29T12:00:00"
    elif case == "bad-ip":
        post["ip"] = "invalid-ip"
    elif case == "wrong-vote":
        after["full_original_vote_scope"]["new_post_votes"][0]["upvote"] = False
    elif case == "two-votes":
        after["full_original_vote_scope"]["new_post_votes"] *= 2
    elif case == "wrong-vote-id":
        after["full_original_vote_scope"]["new_post_votes"][0]["submission_id"] = 4
    elif case == "wrong-vote-time":
        after["full_original_vote_scope"]["new_post_votes"][0][
            "timestamp"
        ] = "2026-10-29T12:00:00"
    elif case == "wrong-excluded-post":
        after["full_original_vote_scope"]["excluded_only_new_post_id"] = 4
    elif case == "wrong-excluded-image":
        after["auxiliary"][
            "excluded_only_new_image_id"
        ] = "22222222-2222-4222-8222-222222222222"
    elif case == "wrong-image-association":
        post["image_id"] = "22222222-2222-4222-8222-222222222222"
    elif case == "wrong-original-bytes":
        next(iter(after["native_media"]["files"].values()))["sha256"] = "e" * 64
    elif case == "wrong-original-dimensions":
        next(iter(after["native_media"]["files"].values()))["dimensions"] = [1280, 853]
    elif case == "unrelated-file":
        after["native_media"]["files"]["unrelated.bin"] = dict(bytes=1, sha256="e" * 64)
    elif case == "wrong-thumbnail":
        image = after["attached_image"]
        after["native_media"]["files"][
            "media/cache/submission_thumbnail_2x/" + image["file_name"]
        ] = dict(bytes=1, sha256="e" * 64, format="JPEG", dimensions=[70, 70])
    else:
        after["native_media"]["directories"].append("unrelated")
    assert current(before, after) is False
    assert oracle()(before, after) is False


@pytest.mark.parametrize(
    "case",
    [
        "missing-table",
        "wrong-policy",
        "missing-key",
        "bool-count",
        "missing-post-column",
        "extra-image-column",
        "missing-auxiliary",
        "invalid-uuid",
        "bad-path",
        "missing-jpeg-metadata",
    ],
)
def test_malformed_or_missing_native_evidence_is_rejected(case: str) -> None:
    after = posted_data()
    if case == "missing-table":
        del after["complete13"]["twelve_task_tables"]["users"]
    elif case == "wrong-policy":
        after["complete13"]["users_only_ignored_column"] = "password"
    elif case == "missing-key":
        del after["complete13"]["submissions"]["key"]
    elif case == "bool-count":
        after["complete13"]["submissions"]["count"] = True
    elif case == "missing-post-column":
        del after["added_posts"][0]["title"]
    elif case == "extra-image-column":
        after["auxiliary"]["all_public_schemas"]["images"].append("unexpected")
    elif case == "missing-auxiliary":
        del after["auxiliary"]["auxiliary"]["notifications"]
    elif case == "invalid-uuid":
        after["attached_image"]["id"] = "bad"
    elif case == "bad-path":
        after["native_media"]["files"]["../outside"] = dict(bytes=1, sha256="e" * 64)
    else:
        del next(iter(after["native_media"]["files"].values()))["dimensions"]
    with pytest.raises(ValueError):
        NativeCapture.model_validate_json(json.dumps(after))


def test_reference_ranges_all_columns_and_empty_digest_boundaries() -> None:
    initial = reference_data()
    parsed = ImageReference.model_validate_json(json.dumps(initial))
    assert ImageReference.model_validate_json(parsed.model_dump_json()) == parsed
    for ranges in [[[2, 1]], [[1, 2], [2, 3]], [[True, 2]], [], [[1, 1]]]:
        value = deepcopy(initial)
        value["known_id_ranges"] = ranges
        with pytest.raises(ValueError):
            ImageReference.model_validate_json(json.dumps(value))
    data = dict(
        count=0,
        columns=["id"],
        key=["id"],
        sha256=__import__("hashlib").sha256(b"").hexdigest(),
    )
    assert SubmissionDigest.model_validate_json(json.dumps(data)).count == 0
    data["sha256"] = "f" * 64
    with pytest.raises(ValueError):
        SubmissionDigest.model_validate_json(json.dumps(data))


def test_native_public_table_order_is_preserved_without_python_collation_assumption() -> (
    None
):
    before = reference_data()
    after = posted_data()
    names = list(reversed(before["capture"]["auxiliary"]["all_public_tables"]))
    before["capture"]["auxiliary"]["all_public_tables"] = names
    after["auxiliary"]["all_public_tables"] = list(names)
    parsed = ImageReference.model_validate_json(json.dumps(before))
    assert parsed.capture.auxiliary.all_public_tables == tuple(names)
    assert current(before, after) is True and oracle()(before, after) is True
