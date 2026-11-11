"""Original complete13/auxiliary/post/vote/media scope, no goal scoring or I/O."""

from datetime import datetime
import ipaddress
from pydantic import JsonValue
from .image_state import ImageReference
from .native_schema import NativeCapture, NativeImage, NativeMedia
from .tasks.image_parameters import PHOTOS


def valid_image(image: NativeImage | None) -> bool:
    if image is None:
        return False
    asset = next((p for p in PHOTOS if p.sha256 == image.sha256), None)
    return bool(
        asset
        and image.file_name == image.sha256 + ".jpg"
        and (image.width, image.height) == asset.dimensions
    )


def media_preserved(
    before: NativeMedia, after: NativeMedia, image: NativeImage | None
) -> bool:
    if before.version != after.version or any(
        after.files.get(n) != v for n, v in before.files.items()
    ):
        return False
    if image is None:
        return before == after
    if not valid_image(image):
        return False
    assert image is not None
    asset = next(p for p in PHOTOS if p.sha256 == image.sha256)
    filename = image.file_name
    original = "submission_images/" + filename
    extra = {n: v for n, v in after.files.items() if n not in before.files}
    file = extra.get(original)
    if file is None or (file.bytes, file.sha256, file.format, file.dimensions) != (
        asset.bytes,
        asset.sha256,
        "JPEG",
        asset.dimensions,
    ):
        return False
    allowed = {
        original,
        "media/cache/submission_thumbnail_1x/" + filename,
        "media/cache/submission_thumbnail_2x/" + filename,
    }
    if not set(extra) <= allowed:
        return False
    for path, value in extra.items():
        if path == original:
            continue
        pixels = 70 if "/submission_thumbnail_1x/" in path else 140
        if (
            value.format != "JPEG"
            or value.dimensions != (pixels, pixels)
            or not 0 < value.bytes <= asset.bytes
        ):
            return False
    allowed_dirs = {
        "submission_images",
        "media",
        "media/cache",
        "media/cache/submission_thumbnail_1x",
        "media/cache/submission_thumbnail_2x",
    }
    return (
        set(before.directories) <= set(after.directories)
        and set(after.directories) - set(before.directories) <= allowed_dirs
    )


def valid_ip(value: JsonValue) -> bool:
    if value is None:
        return True
    if not isinstance(value, (str, int)):
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def author_vote(votes: tuple[dict[str, JsonValue], ...], post: int, user: int) -> bool:
    if len(votes) != 1:
        return False
    row = votes[0]
    ident = row.get("id")
    stamp = row.get("timestamp")
    if (
        set(row) != {"id", "upvote", "timestamp", "user_id", "ip", "submission_id"}
        or type(ident) is not int
        or ident <= 0
        or row.get("upvote") is not True
        or row.get("user_id") != user
        or row.get("submission_id") != post
    ):
        return False
    if not isinstance(stamp, str):
        return False
    try:
        if datetime.fromisoformat(stamp.replace("Z", "+00:00")).tzinfo is None:
            return False
    except ValueError:
        return False
    return valid_ip(row["ip"])


def preserved(initial: ImageReference, terminal: NativeCapture) -> bool:
    b = initial.capture
    a = terminal
    if (
        b.auxiliary.all_public_tables != a.auxiliary.all_public_tables
        or b.auxiliary.all_public_schemas != a.auxiliary.all_public_schemas
        or b.auxiliary.auxiliary != a.auxiliary.auxiliary
        or b.all_original_submissions != a.all_original_submissions
    ):
        return False
    tb = b.complete13.twelve_task_tables
    ta = a.complete13.twelve_task_tables
    if (
        any(ta[n] != tb[n] for n in tb if n != "submission_votes")
        or a.full_original_vote_scope.original != tb["submission_votes"]
    ):
        return False
    if not a.added_posts:
        return (
            a.full_original_vote_scope.excluded_only_new_post_id is None
            and not a.full_original_vote_scope.new_post_votes
            and a.attached_image is None
            and a.complete13 == b.complete13
            and a.native_media == b.native_media
            and a.auxiliary.excluded_only_new_image_id is None
        )
    if len(a.added_posts) != 1:
        return False
    post = a.added_posts[0]
    image = a.attached_image
    uid = initial.account.id
    ident = post.get("id")
    if (
        type(ident) is not int
        or ident <= 0
        or any(lo <= ident <= hi for lo, hi in initial.known_id_ranges)
        or post.get("user_id") != uid
        or post.get("forum_id") not in initial.existing_forum_ids
        or post.get("visibility") != "visible"
        or post.get("body") not in (None, "")
        or post.get("url") is not None
        or post.get("media_type") != "image"
    ):
        return False
    if a.complete13.submissions.count != b.complete13.submissions.count + 1:
        return False
    expected = {
        "comment_count": 0,
        "sticky": False,
        "locked": False,
        "moderated": False,
        "edited_at": None,
        "user_flag": "none",
        "net_score": 1,
    }
    if any(
        post.get(k) != v or type(post.get(k)) is not type(v)
        for k, v in expected.items()
    ):
        return False
    try:
        stamps = []
        for name in ("timestamp", "last_active"):
            text = post.get(name)
            if not isinstance(text, str):
                return False
            stamps.append(datetime.fromisoformat(text.replace("Z", "+00:00")))
        if (
            any(s.tzinfo is None for s in stamps)
            or stamps[0] != stamps[1]
            or type(post.get("ranking")) is not int
        ):
            return False
        if not valid_ip(post.get("ip")):
            return False
        if post.get("search_doc") is not None and not isinstance(
            post["search_doc"], str
        ):
            return False
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    if (
        a.full_original_vote_scope.excluded_only_new_post_id != ident
        or not author_vote(a.full_original_vote_scope.new_post_votes, ident, uid)
    ):
        return False
    if (
        not valid_image(image)
        or image is None
        or post.get("image_id") != image.id
        or a.auxiliary.excluded_only_new_image_id != image.id
    ):
        return False
    if ta["submission_votes"].count != tb["submission_votes"].count + 1:
        return False
    return media_preserved(b.native_media, a.native_media, image)
