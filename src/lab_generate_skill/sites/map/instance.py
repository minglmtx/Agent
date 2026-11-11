"""One private Map preparation and original ten-service lifecycle.

The registered worker must authorize and supervise all effects. This component
keeps its original lease, partial files and service group through failure. Direct
master exits are not whole-resource closure or persistent-state restoration.
No task dispatch, implicit retry, cold replacement or port release is provided.
"""

from collections.abc import Callable
import os
from pathlib import Path
import stat
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.domain.map_services import MapPorts, MapServiceSpec
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.local_ports import LocalPorts, LocalPortLease
from lab_generate_skill.ports.map_services import (
    MapRuntimeFiles,
    MapLayoutWriter,
    MapFrontendFiles,
    MapStartupControls,
)
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from .frontend import MapFrontendPreparation
from .service_controls import controls, validate_host
from .services import MapGeneration


class MapInstance:
    def __init__(
        self,
        inputs: MapRuntimeInputs,
        *,
        files: MapRuntimeFiles,
        ports: LocalPorts,
        layout: MapLayoutWriter,
        frontend_files: MapFrontendFiles,
        commands: NativeCommands,
        services: Callable[[str, OperationControl], NativeServices],
        limits: MapStartupControls,
        hostname: str,
        host_cpus: int,
        expected_web_port: int | None = None,
    ) -> None:
        self.inputs = MapRuntimeInputs.model_validate(inputs)
        validate_host(hostname=hostname, host_cpus=host_cpus)
        self.files, self.ports, self.layout = files, ports, layout
        self.frontend_files, self.commands = frontend_files, commands
        self.services_factory, self.limits = services, limits
        self.hostname, self.host_cpus = hostname, host_cpus
        if expected_web_port is not None and (
            type(expected_web_port) is not int or not 1024 <= expected_web_port <= 65535
        ):
            raise ValueError("Exact original unprivileged web port required")
        self.expected_web_port = expected_web_port
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.lease: LocalPortLease | None = None
        self.spec: MapServiceSpec | None = None
        self.removed_private_pids: tuple[str, ...] | None = None
        self.frontend: MapFrontendPreparation | None = None
        self.group: NativeServices | None = None
        self.generation: MapGeneration | None = None
        self.primary_error: BaseException | None = None
        self.cleanup_error: BaseException | None = None
        self.stop_attempted = False
        self.stop_facts: tuple[NativeServiceExit, ...] | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original Map instance worker/thread required")

    def prepare(self, control: OperationControl) -> MapServiceSpec:
        self._owner()
        if self.state != "new":
            raise InvalidTransition("Original Map preparation cannot be repeated")
        control.checkpoint()
        self.state = "preparing"
        try:
            if self.expected_web_port is None:
                self.files.stage(self.inputs, control)
            self.lease = self.ports.reserve(6, control)
            leased = self.lease.ports
            if type(leased) is not tuple or len(leased) != 6:
                raise ValueError("Original Map lease requires six exact ports")
            if self.expected_web_port is not None:
                if leased[0] != self.expected_web_port:
                    raise OwnershipConflict(
                        "Map lease changed exact original source web port"
                    )
                self.files.stage(self.inputs, control)
            self.spec = MapServiceSpec(
                inputs=self.inputs,
                ports=MapPorts(
                    web=leased[0],
                    search=leased[1],
                    car=leased[2],
                    bike=leased[3],
                    foot=leased[4],
                    tiles=leased[5],
                ),
            )
            self.removed_private_pids = self.layout.prepare(
                self.spec,
                controls(self.spec, hostname=self.hostname, host_cpus=self.host_cpus),
                control,
            )
            self.frontend = MapFrontendPreparation(self.spec, self.frontend_files)
            self.frontend.prepare(control)
            control.checkpoint()
            self.state = "prepared"
            return self.spec
        except BaseException as error:
            self.primary_error = error
            self.state = "failed"
            raise

    def start(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "prepared" or self.spec is None:
            raise InvalidTransition("Map start requires original prepared instance")
        control.checkpoint()
        self.state = "starting"
        try:
            root = Path(self.inputs.files.log_root)
            info = root.lstat()
            if (
                root.resolve(strict=True) != root
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise OwnershipConflict("Original private Map log root required")
            log = root / "generation-1"
            log.mkdir(mode=0o700)
            # Factory only constructs an owned group; it must not launch services.
            # Retain that group even if generation construction/start fails.
            self.group = self.services_factory(str(log), control)
            self.generation = MapGeneration(
                self.spec, self.commands, self.group, self.limits
            )
            endpoint = self.generation.start(control)
            control.checkpoint()
            self.state = "ready"
            return endpoint
        except BaseException as error:
            self.primary_error = error
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._owner()
        if self.stop_facts is not None:
            return self.stop_facts
        if self.stop_attempted:
            raise InvalidTransition(
                "Uncertain Map stop cannot be replayed; retain original resource owner"
            ) from self.cleanup_error
        self.stop_attempted = True
        self.state = "stopping"
        try:
            if self.generation is not None:
                facts = self.generation.stop(control)
            elif self.group is not None:
                facts = self.group.stop(control)
            else:
                control.checkpoint()
                facts = ()
            self.stop_facts = facts
            self.state = "stopped"
            return facts
        except BaseException as error:
            self.cleanup_error = error
            self.state = "failed"
            raise
