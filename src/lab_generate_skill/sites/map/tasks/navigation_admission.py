"""Canonical selected navigation bytes; no execution permission or admission."""

from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.map_navigation_scope import check_navigation_scope
from lab_generate_skill.domain.errors import OwnershipConflict
from .navigation_spec import NavigationSpec


def task_input(request: SiteTaskRequest) -> NavigationSpec:
    value = NavigationSpec.model_validate_json(request.private_input)
    if value.model_dump_json() != request.private_input or value.task != request.task:
        raise OwnershipConflict(
            "Navigation private input changed original canonical task"
        )
    check_navigation_scope(value.task, value.native_contract_ref.sha256)
    return value
