"""Fixed native startup phases; no paths, credentials or task payloads."""

from collections.abc import Callable
from enum import Enum


class GitlabPhase(str, Enum):
    IMAGE_BEGIN = "image_stage_begin"
    IMAGE_READY = "image_stage_ready"
    SEED_BEGIN = "seed_begin"
    SEED_READY = "seed_ready"
    BACKEND_BEGIN = "backend_begin"
    BACKEND_READY = "backend_ready"
    FRONTEND_BEGIN = "frontend_begin"
    FRONTEND_READY = "frontend_ready"


GitlabProgress = Callable[[GitlabPhase], None]
