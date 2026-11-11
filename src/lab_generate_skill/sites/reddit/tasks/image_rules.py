"""Original conditional native-image goal checks after full mutation protection."""

from urllib.parse import urlsplit
from ..image_protection import preserved
from ..image_state import ImageReference
from ..native_schema import NativeCapture
from ..evidence_schema import RedditPageHealth, ImageOutcome, CHECKS
from .image_spec import NativeImageSpec


def decide_image(
    spec: NativeImageSpec,
    reference: ImageReference | None,
    after: NativeCapture | None,
    page: RedditPageHealth | None,
    last_issued_ax: str | None,
    *,
    site_origin: str,
    runtime_error: bool = False,
) -> ImageOutcome:
    def unknown(reason: str) -> ImageOutcome:
        return ImageOutcome(
            "unknown", None, tuple((name, None) for name in CHECKS), reason
        )

    spec = NativeImageSpec.model_validate(spec)
    if type(runtime_error) is not bool:
        raise ValueError("Explicit original runtime status required")
    if runtime_error or reference is None or after is None:
        return unknown("INCOMPLETE_NATIVE_STATE")
    reference = ImageReference.model_validate(reference)
    after = NativeCapture.model_validate(after)
    if not preserved(reference, after):
        return unknown("NATIVE_MUTATION_SCOPE_FAILED")
    if page is None:
        return unknown("MISSING_TERMINAL_DOCUMENT")
    page = RedditPageHealth.model_validate(page)
    if page.http_status is None:
        return unknown("MISSING_DOCUMENT_TRANSPORT")
    if page.http_status >= 500:
        return unknown("TERMINAL_SERVER_ERROR")
    actual, origin = urlsplit(page.url), urlsplit(site_origin)
    values = [
        200 <= page.http_status < 300
        and (actual.scheme, actual.netloc) == (origin.scheme, origin.netloc)
        and not page.login_page
        and not page.error_page,
        len(after.added_posts) == 1,
    ]
    if len(after.added_posts) == 1:
        if type(last_issued_ax) is not str:
            return unknown("MISSING_ISSUED_OBSERVATION")
        post, image, p = after.added_posts[0], after.attached_image, spec.parameters
        values += [
            post.get("user_id") == reference.account.id,
            post.get("forum_id") == reference.target_forum.id,
            post.get("title") == p.title,
            post.get("media_type") == "image"
            and post.get("url") is None
            and image is not None,
            bool(image and image.sha256 == p.image_sha256),
            p.title in last_issued_ax,
        ]
    passed = all(values)
    return ImageOutcome(
        "success" if passed else "failure",
        int(passed),
        tuple(zip(CHECKS[: len(values)], values, strict=True)),
        "ALL_NATIVE_IMAGE_CHECKS_MATCH" if passed else "NATIVE_IMAGE_GOAL_MISMATCH",
    )
