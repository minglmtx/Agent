"""Fixed diagnostic labels only; never arguments, paths or task/model inputs."""

from enum import Enum
from collections.abc import Callable


class ShoppingPhase(str, Enum):
    IMAGE_BEGIN = "image_stage_begin"
    IMAGE_READY = "image_stage_ready"
    SEED_BEGIN = "seed_begin"
    SEED_READY = "seed_ready"
    BACKEND_BEGIN = "backend_begin"
    BACKEND_READY = "backend_ready"
    CONFIGURE_BEGIN = "configure_begin"
    CONFIGURE_READY = "configure_ready"
    FRONTEND_BEGIN = "frontend_begin"
    FRONTEND_READY = "frontend_ready"


ShoppingProgress = Callable[[ShoppingPhase], None]
