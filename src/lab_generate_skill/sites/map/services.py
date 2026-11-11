"""One original ten-service generation using shared owned command/process ports.

The caller must stage and prepare original frontend sources before start. This
class does not admit a task or prove restoration/resource closure.
"""

import os
from pathlib import Path
import stat
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.domain.map_services import MapServiceSpec
from .service_commands import SERVICE_NAMES, service_commands, setup_commands
from .service_readiness import MapReadiness
from .tile_style import rebind_style
from .service_controls import sample_tile_path
from lab_generate_skill.ports.map_services import MapStartupControls


class MapGeneration:
    def __init__(
        self,
        spec: MapServiceSpec,
        commands: NativeCommands,
        services: NativeServices,
        limits: MapStartupControls,
    ) -> None:
        self.spec = MapServiceSpec.model_validate(spec)
        self.commands, self.services = commands, services
        self.limits = limits
        self.health = MapReadiness(self.spec, commands, services, limits)
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.pins: tuple[NativeNamespaceIdentity, ...] = ()
        self.tile_sample: bytes | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original Map service generation owner required")

    def start(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "new":
            raise InvalidTransition("Original Map generation starts only once")
        control.checkpoint()
        self.state = "starting"
        argv, setup = service_commands(self.spec), setup_commands(self.spec)

        def launch(name: str) -> None:
            self.services.start(name, argv[name], control)

        def pin(name: str) -> None:
            self.pins += (self.services.pin_namespace(name, control),)

        def run(name: str) -> None:
            self.services.require_running()
            bound = self.limits.bind(
                control, "copy_modules" if name == "copy_modules" else "setup"
            )
            self.commands.run(setup[name], bound)

        try:
            launch("search_postgres")
            self.health.postgres("nominatim", control)
            pin("search_postgres")
            run("search_refresh")
            launch("search_http")
            self.health.http(
                self.spec.ports.search,
                "/search?q=Pittsburgh&format=jsonv2&limit=1",
                control,
            )
            pin("search_http")
            for profile in ("car", "bike", "foot"):
                launch("route_" + profile)
            for profile, port in zip(
                ("car", "bike", "foot"),
                (self.spec.ports.car, self.spec.ports.bike, self.spec.ports.foot),
                strict=True,
            ):
                self.health.http(
                    port,
                    "/route/v1/driving/-73.9857,40.7484;-73.9654,40.7829?overview=false&steps=false",
                    control,
                )
                pin("route_" + profile)
            launch("tile_postgres")
            self.health.postgres("tiles", control)
            pin("tile_postgres")
            run("copy_style")
            run("compile_style")
            rebind_style(
                Path(self.spec.state_root("tiles")) / "style/mapnik.xml", control
            )
            launch("renderd")
            socket = Path(self.spec.state_root("tiles")) / "run/renderd.sock"
            socket_control = self.limits.bind(control, "renderd")
            while True:
                socket_control.checkpoint()
                self.services.require_running()
                if os.path.lexists(socket):
                    if socket.resolve(strict=True) != socket or not stat.S_ISSOCK(
                        socket.lstat().st_mode
                    ):
                        raise ValueError(
                            "Original private renderd Unix socket required"
                        )
                    break
                socket_control.wait(0.1)
            pin("renderd")
            run("apache_check")
            launch("tile_http")
            path = sample_tile_path()
            first = self.health.http(self.spec.ports.tiles, path, control, seconds=90)
            second = self.health.http(self.spec.ports.tiles, path, control, seconds=30)
            self.tile_sample = first
            if (
                not first.startswith(b"\x89PNG\r\n\x1a\n")
                or len(first) < 1000
                or first != second
            ):
                raise ValueError("Original full native tile/cache probes differ")
            pin("tile_http")
            launch("app_postgres")
            self.health.postgres("db", control)
            pin("app_postgres")
            run("copy_modules")
            run("bundle_check")
            launch("rails_server")
            self.health.http(self.spec.ports.web, "/", control, first_rails=True)
            pin("rails_server")
            self.services.require_running()
            if tuple(p.service for p in self.pins) != SERVICE_NAMES:
                raise ValueError(
                    "Original ten native service namespace identities differ"
                )
            self.state = "running"
            return self.spec.endpoint
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._owner()
        self.state = "stopping"
        try:
            facts = self.services.stop(control)
            self.state = "stopped"
            return facts
        except BaseException:
            self.state = "failed"
            raise
