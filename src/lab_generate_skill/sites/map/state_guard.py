"""Original write guard, full native observation and unchanged-state check.

This is not a reset implementation: unchanged reuse additionally needs the
original Rails restart and post-restart check. Changed state requires a newly
owned cold instance. SQL/capture faults poison this guard and are never retried.
"""

from dataclasses import dataclass
import os
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_state import MapPersistentState
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state import MapPersistentFiles
from lab_generate_skill.ports.map_services import MapStartupControls
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from .service_commands import container
from .state_sql import INSTALL_SQL, STATE_SQL
from .state_rules import database_state, fingerprint


class MapStateChanged(RuntimeError):
    """Original complete state differs; cannot clear tracking or reuse this site."""


@dataclass(frozen=True)
class MapGuardObservation:
    database: bytes
    persistent: MapPersistentState
    sha256: str


class MapStateGuard:
    def __init__(
        self,
        spec: MapServiceSpec,
        commands: NativeInputCommands,
        files: MapPersistentFiles,
        services: NativeServices,
        limits: MapStartupControls,
    ) -> None:
        self.spec = MapServiceSpec.model_validate(spec)
        self.commands, self.files, self.services, self.limits = (
            commands,
            files,
            services,
            limits,
        )
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.initial: MapGuardObservation | None = None
        self.observations: list[MapGuardObservation] = []
        self.error: BaseException | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original Map state guard worker/thread required")

    def _sql(self, sql: str, control: OperationControl) -> bytes:
        self.services.require_running()
        command = container(self.spec, "db") + (
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            "/state/run",
            "-U",
            "openstreetmap",
            "-d",
            "openstreetmap",
        )
        result = self.commands.run_input(
            command, sql.encode(), self.limits.bind(control, "state_sql")
        )
        self.services.require_running()
        return result

    def _capture(self, control: OperationControl) -> MapGuardObservation:
        data = self._sql(STATE_SQL, control)
        database_state(data)  # malformed SQL cannot silently become an empty DB
        persistent = MapPersistentState.model_validate(
            self.files.capture(self.spec, control)
        )
        result = MapGuardObservation(data, persistent, fingerprint(persistent, data))
        self.observations.append(result)
        self.services.require_running()
        control.checkpoint()
        return result

    def install(self, control: OperationControl) -> MapGuardObservation:
        self._owner()
        if self.state != "new":
            raise InvalidTransition(
                "Original Map write guard installation cannot repeat"
            )
        control.checkpoint()
        self.state = "installing"
        try:
            self._sql(INSTALL_SQL, control)
            initial = self._capture(control)
            if database_state(initial.database)["changed"]:
                raise MapStateChanged(
                    "Native persistent write occurred during Map guard installation"
                )
            self.initial = initial
            self.state = "ready"
            return initial
        except BaseException as error:
            self.error = error
            self.state = "failed"
            raise

    def require_unchanged(self, control: OperationControl) -> MapGuardObservation:
        self._owner()
        if self.state != "ready" or self.initial is None:
            raise InvalidTransition("Original healthy installed Map guard required")
        control.checkpoint()
        self.state = "observing"
        try:
            result = self._capture(control)
            if result.sha256 != self.initial.sha256:
                raise MapStateChanged(
                    "Map persistent state changed; cold deployment required"
                )
            self.state = "ready"
            return result
        except BaseException as error:
            self.error = error
            self.state = "changed" if isinstance(error, MapStateChanged) else "failed"
            raise
