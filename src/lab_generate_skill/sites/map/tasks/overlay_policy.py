"""Required selected Map coverage; declarations grant no environment/Actor rights."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from .overlay_spec import SOURCE

PREPARATION_CHECKS = (
    "map.overlay.original_spec",
    "map.overlay.original_snapshot",
    "map.overlay.complete_state_unchanged",
)


def overlay_initial_spec(task: TaskIdentity) -> InitialStateSpec:
    if (
        task.site,
        task.family,
        task.contract_version,
        task.split,
        task.task_id,
        task.source_task_id,
    ) != ("map", "native_route_map_data", 1, "train", SOURCE, SOURCE):
        raise ValueError("Only selected original train MapData coverage supported")
    return InitialStateSpec(
        spec_id="map-native-route-overlay-state-v1",
        task=task,
        environment_checks=(
            "map.instance.original",
            "map.ten_services.initial_ready",
            "map.geographic_baseline.complete",
            "map.native_guard.complete",
        ),
        preparation_checks=PREPARATION_CHECKS,
        initial_checks=("map.initial.observation", "map.initial.native_ready"),
        equivalence_checks=("map.initial.equivalence",),
        task_reset_checks=(
            "map.complete_state.unchanged",
            "map.original_frontend.retired",
        ),
        environment_reset_checks=("map.original_frontend.resumed",),
        health_checks=("map.backends.ready", "map.frontend.ready"),
    )
