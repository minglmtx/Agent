"""Existing deadline intersection for the selected original startup phases."""

from lab_generate_skill.ports.map_services import MapStartupPhase
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.combined_control import CombinedControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl

LIMITS = {
    "postgres": 120,
    "postgres_probe": 10,
    "http": 180,
    "tile_first": 90,
    "tile_second": 30,
    "renderd": 90,
    "setup": 180,
    "copy_modules": 300,
    "state_sql": 60,
    "frontend_grace": 30,
    "frontend_force": 10,
    "database_reference": 180,
}


class BoundedMapStartupControls:
    def bind(
        self, caller: OperationControl, phase: MapStartupPhase
    ) -> OperationControl:
        if type(phase) is not str or phase not in LIMITS:
            raise ValueError("Explicit original Map startup phase required")
        return CombinedControl(caller, DeadlineControl(LIMITS[phase], "map-" + phase))
