"""Existing coherent Shopping fake effects, with original category parameters."""

from pathlib import Path
from typing import Literal
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping.worker_instance import ShoppingWorkerInstance
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from shopping_task_fixtures import case, request as eta_request, QueryCommands
from test_shopping_category_navigation_input import reference


def worker(root: Path) -> tuple[ShoppingWorkerInstance, QueryCommands]:
    root.mkdir(exist_ok=True)
    original, commands, _ = case(root)

    def forbidden_customer(control: object) -> str:
        raise AssertionError("Category preparation must not acquire ETA customer/date")

    return ShoppingWorkerInstance(original.instance, forbidden_customer), commands


def request(
    raw: bytes,
    public: PublicTask,
    *,
    action: Literal["snapshot", "prepare", "inspect", "restore"] = "snapshot",
    operation_id: str = "category-snapshot",
    snapshot_ref: EvidenceRef | None = None,
) -> SiteTaskRequest:
    spec = load_category_navigation_inputs(raw, reference(raw), public).private_spec
    original = eta_request(action, operation_id, snapshot_ref)
    return SiteTaskRequest.model_validate(
        {
            **original.model_dump(),
            "task": spec.task,
            "private_input": CategoryNavigationExecutionInput(
                spec=spec
            ).model_dump_json(),
        }
    )
