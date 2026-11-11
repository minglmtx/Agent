"""Fixed private lifecycle phase names; no task values or file contents."""

from collections.abc import Callable
from enum import Enum


class RedditPhase(str, Enum):
    IMAGE_BEGIN = "image_begin"
    IMAGE_READY = "image_ready"
    SEED_BEGIN = "seed_begin"
    SEED_READY = "seed_ready"
    BACKEND_BEGIN = "backend_begin"
    BACKEND_READY = "backend_ready"
    FRONTEND_READY = "frontend_ready"
    SNAPSHOT_BEGIN = "snapshot_begin"
    SNAPSHOT_READY = "snapshot_ready"
    RESTORE_BEGIN = "restore_begin"
    RESTORE_READY = "restore_ready"
    RESUME_BEGIN = "resume_begin"
    RESUME_READY = "resume_ready"


RedditProgress = Callable[[RedditPhase], None]
