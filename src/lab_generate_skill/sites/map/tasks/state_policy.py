"""Explicit selected task policies over one original physical Map environment."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from .overlay_policy import overlay_initial_spec
from .navigation_policy import navigation_initial_spec


def map_initial_spec(
    task: TaskIdentity, native_contract_sha256: str | None = None
) -> InitialStateSpec:
    task = TaskIdentity.model_validate(task)
    if task.family == "native_route_map_data":
        return overlay_initial_spec(task)
    if task.family == "navigation_page_identity" and native_contract_sha256 is not None:
        return navigation_initial_spec(task, native_contract_sha256)
    raise ValueError("Explicit supported Map task and original contract pin required")
