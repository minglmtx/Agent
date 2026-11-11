"""Selected Map preparation and intersected startup deadlines, no authority."""

from typing import Literal, Protocol
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.domain.map_frontend import MapFrontendPlan, MapFrontendPrepared
from .lifecycle import OperationControl

MapStartupPhase = Literal[
    "postgres",
    "postgres_probe",
    "http",
    "tile_first",
    "tile_second",
    "renderd",
    "setup",
    "copy_modules",
    "state_sql",
    "frontend_grace",
    "frontend_force",
    "database_reference",
]


class MapRuntimeFiles(Protocol):
    def stage(self, plan: MapRuntimeInputs, control: OperationControl) -> None:
        """Clone only fixed published inputs into the original acquired fresh root.

        Retain partial files on failure; no reuse, overwrite or implicit cleanup.
        The enclosing registered worker supplies authority and hard supervision.
        """
        ...


class MapStartupControls(Protocol):
    def bind(
        self, caller: OperationControl, phase: MapStartupPhase
    ) -> OperationControl:
        """Intersect original finite phase with original caller cancellation/deadline."""
        ...


class MapLayoutWriter(Protocol):
    def prepare(
        self, spec: MapServiceSpec, content: dict[str, str], control: OperationControl
    ) -> tuple[str, ...]:
        """Validate original baseline; create fresh controls; report removed private PIDs."""
        ...


class MapFrontendFiles(Protocol):
    def read(self, spec: MapServiceSpec, control: OperationControl) -> dict[str, bytes]:
        """Read exact selected original pins from the private published-input clone."""
        ...

    def apply(
        self, plan: MapFrontendPlan, control: OperationControl
    ) -> MapFrontendPrepared:
        """Reserve once, retain originals and apply selected private changes; never retry."""
        ...
