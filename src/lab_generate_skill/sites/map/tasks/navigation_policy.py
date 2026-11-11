"""Exact complete selected navigation subgroup, on existing physical state gates."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.map_navigation_scope import check_navigation_scope
from lab_generate_skill.domain.state_checks import InitialStateSpec

from lab_generate_skill.domain.map_navigation_scope import (
    NAVIGATION_PAGE_MEMBERS as MEMBERS,
)

PREPARATION_CHECKS = (
    "map.navigation.original_spec",
    "map.navigation.original_snapshot",
    "map.navigation.complete_state_unchanged",
)


def navigation_initial_spec(
    task: TaskIdentity, native_contract_sha256: str
) -> InitialStateSpec:
    task = TaskIdentity.model_validate(task)
    check_navigation_scope(task, native_contract_sha256)
    if task.source_task_id not in MEMBERS:
        raise ValueError(
            "Only complete selected navigation subgroup has preparation coverage"
        )
    return InitialStateSpec(
        spec_id="map-navigation-page-state-v1",
        task=task,
        environment_checks=(
            "map.instance.original",
            "map.ten_services.initial_ready",
            "map.geographic_baseline.complete",
            "map.native_guard.complete",
        ),
        preparation_checks=PREPARATION_CHECKS,
        initial_checks=(
            "map.navigation.initial.observation",
            "map.navigation.initial.document_ready",
        ),
        equivalence_checks=("map.navigation.initial.equivalence",),
        task_reset_checks=(
            "map.complete_state.unchanged",
            "map.original_frontend.retired",
        ),
        environment_reset_checks=("map.original_frontend.resumed",),
        health_checks=("map.backends.ready", "map.frontend.ready"),
    )
