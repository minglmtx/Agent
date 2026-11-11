"""Complete synthetic native facts, with real declared photo metadata only."""

from copy import deepcopy
import hashlib
from typing import Any
from lab_generate_skill.sites.reddit.native_schema import NATIVE13, TABLES12
from lab_generate_skill.sites.reddit.tasks.image_parameters import PHOTOS

COLUMNS = [
    "id",
    "forum_id",
    "user_id",
    "title",
    "url",
    "body",
    "image_id",
    "media_type",
    "visibility",
    "comment_count",
    "sticky",
    "locked",
    "moderated",
    "edited_at",
    "user_flag",
    "net_score",
    "timestamp",
    "last_active",
    "ranking",
    "ip",
    "search_doc",
]
IMAGE_ID = "11111111-1111-4111-8111-111111111111"
STAMP = "2026-10-29T12:00:00+00:00"


def reference_data() -> dict[str, Any]:
    names = sorted(NATIVE13 | {"images", "notifications"})
    schemas = {name: ["id"] for name in names}
    schemas["submissions"] = list(COLUMNS)
    schemas["images"] = ["id", "file_name", "sha256", "width", "height"]
    schemas["notifications"] = ["id", "user_id", "body"]
    tables = {name: {"count": 10, "digest": "a" * 32} for name in TABLES12}
    subs = dict(count=2, columns=list(COLUMNS), key=["id"], sha256="b" * 64)
    aux = {
        name: dict(
            columns=schemas[name], count=0, digest=hashlib.md5(b"0:0:0:0").hexdigest()
        )
        for name in ["images", "notifications"]
    }
    capture = dict(
        complete13=dict(
            version="reddit45-readonly-complete13-v1",
            twelve_task_tables=tables,
            submissions=subs,
            users_only_ignored_column="last_seen",
        ),
        all_original_submissions=deepcopy(subs),
        auxiliary=dict(
            all_public_tables=names,
            all_public_schemas=schemas,
            auxiliary=aux,
            excluded_only_new_image_id=None,
        ),
        added_posts=[],
        attached_image=None,
        full_original_vote_scope=dict(
            original=deepcopy(tables["submission_votes"]),
            new_post_votes=[],
            excluded_only_new_post_id=None,
        ),
        native_media=dict(
            version="reddit-native-media-storage-candidate-v2", directories=[], files={}
        ),
    )
    return dict(
        version="reddit-native-real-photo-candidate-v1",
        account=dict(id=17, username="native-user"),
        target_forum=dict(id=1, name="EarthPorn"),
        existing_forum_ids=[1, 2],
        known_id_ranges=[[1, 2]],
        capture=capture,
    )


def posted_data(photo_index: int = 0) -> dict[str, Any]:
    base = reference_data()
    result: dict[str, Any] = deepcopy(base["capture"])
    photo = PHOTOS[photo_index]
    row = dict(
        id=3,
        forum_id=1,
        user_id=17,
        title="Beautiful Sunset at the Beach",
        url=None,
        body="",
        image_id=IMAGE_ID,
        media_type="image",
        visibility="visible",
        comment_count=0,
        sticky=False,
        locked=False,
        moderated=False,
        edited_at=None,
        user_flag="none",
        net_score=1,
        timestamp=STAMP,
        last_active=STAMP,
        ranking=123,
        ip="127.0.0.1",
        search_doc=None,
    )
    result["added_posts"] = [row]
    result["attached_image"] = dict(
        id=IMAGE_ID,
        file_name=photo.sha256 + ".jpg",
        sha256=photo.sha256,
        width=photo.dimensions[0],
        height=photo.dimensions[1],
    )
    result["complete13"]["submissions"].update(count=3, sha256="c" * 64)
    result["complete13"]["twelve_task_tables"]["submission_votes"].update(
        count=11, digest="c" * 32
    )
    result["full_original_vote_scope"].update(
        new_post_votes=[
            dict(
                id=101,
                upvote=True,
                timestamp=STAMP,
                user_id=17,
                ip="127.0.0.1",
                submission_id=3,
            )
        ],
        excluded_only_new_post_id=3,
    )
    result["auxiliary"]["excluded_only_new_image_id"] = IMAGE_ID
    result["native_media"]["directories"] = ["submission_images"]
    result["native_media"]["files"]["submission_images/" + photo.sha256 + ".jpg"] = (
        dict(
            bytes=photo.bytes,
            sha256=photo.sha256,
            format="JPEG",
            dimensions=list(photo.dimensions),
        )
    )
    return result
