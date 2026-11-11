"""One original private Admin service startup, below SiteProvider admission.

Owner must pre-register resources, verify staged image/path ownership and reserve
ports before constructing. Each effect is once only; failure retains partial
state and service handles for stop under a separate cleanup control. This leaf
never creates task fixtures, observation/baseline receipts or closure authority.
"""

from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from .artifact_io import checked_path
from .service_contract import AdminServiceSpec
from .service_commands import container, service_commands
from .service_files import write_service_files
from .service_programs import CONFIGURE, HEALTH, SEED
from .frontend import AdminFrontend
from .initial_search import INITIAL_SEARCH_HOLD_PHP, hold_initial_search
from lab_generate_skill.domain.admin_navigation_origin import AdminNavigationOrigin
from .database_observer import (
    require_private_node,
    prepare_observer,
    require_initial_idle,
)


class AdminLocalServices:
    def __init__(
        self,
        spec: AdminServiceSpec,
        commands: NativeCommands,
        services: NativeServices,
        *,
        navigation_origin: AdminNavigationOrigin | None = None,
    ) -> None:
        self.spec = AdminServiceSpec.model_validate(spec)
        self.navigation_origin = (
            None
            if navigation_origin is None
            else AdminNavigationOrigin.model_validate(navigation_origin)
        )
        if (
            self.navigation_origin is not None
            and self.navigation_origin.endpoint != self.spec.admin_url
        ):
            raise ValueError("Initial search hold changed original navigation origin")
        self.commands, self.services = commands, services
        self.frontend = AdminFrontend(self.spec, commands, services)
        self.state: Literal[
            "new",
            "preparing",
            "prepared",
            "starting",
            "ready",
            "failed",
            "stopping",
            "stopped",
        ] = "new"

    def prepare(self, control: OperationControl) -> None:
        if self.state != "new":
            raise RuntimeError("Private seed preparation was already attempted")
        control.checkpoint()
        self.state = "preparing"
        try:
            require_private_node(self.spec, control)
            state = Path(self.spec.layout.state_root)
            checked_path(state, control)
            if not state.is_dir() or any(state.iterdir()):
                raise ValueError("Fresh empty private state directory required")
            if self.navigation_origin is not None:
                self.commands.run(
                    container(self.spec, seeded=False)
                    + ("php", "-r", "if(false){" + INITIAL_SEARCH_HOLD_PHP + "}"),
                    control,
                )
            self.commands.run(
                container(self.spec, seeded=False) + ("sh", "-ec", SEED), control
            )
            prepare_observer(self.spec, self.commands, control)
            write_service_files(self.spec, control)
            # Fail configuration dependencies before launching any service.
            base = container(self.spec)
            self.commands.run(
                base
                + (
                    "nginx",
                    "-t",
                    "-e",
                    "/state/nginx-error.log",
                    "-c",
                    "/state/nginx.conf",
                ),
                control,
            )
            self.commands.run(
                base + ("php-fpm", "-t", "--fpm-config", "/state/php-fpm.conf"), control
            )
            self.state = "prepared"
        except BaseException:
            self.state = "failed"
            raise

    def _wait(
        self, stage: Literal["backend", "frontend"], control: OperationControl
    ) -> None:
        ports = self.spec.ports
        while True:
            remaining = control.checkpoint()
            args = (
                (stage, str(ports.redis), str(ports.search))
                if stage == "backend"
                else (stage, str(ports.web), str(remaining))
            )
            self.services.require_running()
            reply = self.commands.run(
                container(self.spec) + ("php", "-r", HEALTH, *args), control
            )
            if reply == b"ready":
                return
            if reply != b"waiting":
                raise ValueError("Malformed native health reply")
            control.wait(0.25)

    def start(self, control: OperationControl) -> str:
        if self.state != "prepared":
            raise RuntimeError("Start requires this original prepared private seed")
        control.checkpoint()
        self.state = "starting"
        try:
            argv = service_commands(self.spec)
            for name in ("mysql", "redis", "search"):
                self.services.start(name, argv[name], control)
            if self.navigation_origin is not None:
                self.services.require_running()
                hold_initial_search(self.spec, self.commands, control)
                self.services.require_running()
            self._wait("backend", control)
            require_initial_idle(self.spec, self.commands, control)
            ports = self.spec.ports
            reply = self.commands.run(
                container(self.spec)
                + (
                    "php",
                    "-r",
                    CONFIGURE,
                    str(ports.database),
                    str(ports.redis),
                    str(ports.web),
                    str(ports.search),
                ),
                control,
            )
            if reply != b"configured":
                raise ValueError("Malformed native configuration reply")
            self.commands.run(
                container(self.spec)
                + ("php", "/var/www/magento2/bin/magento", "cache:flush"),
                control,
            )
            for name in ("php", "nginx"):
                self.services.start(name, argv[name], control)
            self._wait("frontend", control)
            self.frontend.pin(control)
            control.checkpoint()
            self.state = "ready"
            return self.spec.admin_url
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.state = "stopping"
        try:
            facts = self.services.stop(control)
            if any(f.state != "reaped" for f in facts):
                error = RuntimeError(
                    "Original Admin service launchers remain unconfirmed"
                )
                setattr(error, "service_exits", facts)
                raise error
            self.state = "stopped"
            return facts
        except BaseException:
            self.state = "failed"
            raise
