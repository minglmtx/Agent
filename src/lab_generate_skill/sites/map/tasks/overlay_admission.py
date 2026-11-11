"""Selected original inputs and persisted snapshot binding, not task authority."""

from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from .overlay_spec import NativeOverlaySpec


def task_input(request: SiteTaskRequest) -> NativeOverlaySpec:
    value = NativeOverlaySpec.model_validate_json(request.private_input)
    if value.model_dump_json() != request.private_input or value.task != request.task:
        raise OwnershipConflict("Map private input changed original canonical task")
    return value
