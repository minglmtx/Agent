"""Canonical private Group input on the existing task request boundary."""

from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from .group_spec import GroupSpec


def task_input(request: SiteTaskRequest) -> GroupSpec:
    spec = GroupSpec.model_validate_json(request.private_input)
    if spec.model_dump_json() != request.private_input or spec.task != request.task:
        raise OwnershipConflict("Group input changed original canonical task")
    return spec
