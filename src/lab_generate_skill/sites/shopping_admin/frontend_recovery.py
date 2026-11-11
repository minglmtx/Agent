"""Once-only frontend recovery after original closure and completed state restore.

New explicit service names retain all previous children and namespace handles in
the original service group. No replacement backend, implicit retry, configuration
rewrite, port release, new task permission, or whole-site ResetReceipt.
"""

import hashlib
from typing import Protocol
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from .state_contract import AdminStateRestored
from .frontend_contract import AdminFrontendStopped
from .frontend_recovery_contract import AdminFrontendRecovered
from .backend_drain import AdminDrain
from .service_commands import container, service_commands
from .service_programs import HEALTH


class FrontendRecoveryAuthority(Protocol):
    def verify(
        self,
        stopped: AdminFrontendStopped,
        restored: AdminStateRestored,
        control: OperationControl,
    ) -> None:
        """Verify original completed restore, browser closure, sole writer and lease.

        Neither serialized descriptors nor a cleanup operation imply permission
        to launch this generation. No default approval or repeat after unknown.
        """
        ...


class AdminFrontendRecovery:
    def __init__(
        self,
        stopped: AdminFrontendStopped,
        restored: AdminStateRestored,
        *,
        commands: NativeCommands,
        services: NativeServices,
        authority: FrontendRecoveryAuthority,
    ) -> None:
        self.stopped = AdminFrontendStopped.model_validate(stopped)
        self.restored = AdminStateRestored.model_validate(restored)
        if self.restored.cache.service != self.stopped.service:
            raise ValueError("Recovery changed original service instance")
        self.commands, self.services, self.authority = commands, services, authority
        self.attempted = False
        self.start_attempted: list[str] = []
        self.launched: list[str] = []
        self.pins: list[NativeNamespaceIdentity] = []
        self.result: AdminFrontendRecovered | None = None

    def recover(self, control: OperationControl) -> AdminFrontendRecovered:
        if self.attempted:
            raise RuntimeError(
                "Frontend recovery already attempted; never restart after unknown"
            )
        control.checkpoint()
        self.authority.verify(self.stopped, self.restored, control)
        control.checkpoint()
        self.attempted = True
        spec = self.stopped.service
        base = container(spec)
        try:
            drained = AdminDrain(spec, self.commands).wait(control)
            if (
                self.commands.run(
                    base
                    + (
                        "php",
                        "-r",
                        HEALTH,
                        "backend",
                        str(spec.ports.redis),
                        str(spec.ports.search),
                    ),
                    control,
                )
                != b"ready"
            ):
                raise RuntimeError("Original restored backends are not ready")
            # Read-only configuration tests precede either new namespace.
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
            argv = service_commands(spec)
            for logical in ("php", "nginx"):
                name = logical + "-restored"
                self.start_attempted.append(name)
                self.services.start(name, argv[logical], control)
                self.launched.append(name)
            while True:
                remaining = control.checkpoint()
                result = self.commands.run(
                    base
                    + (
                        "php",
                        "-r",
                        HEALTH,
                        "frontend",
                        str(spec.ports.web),
                        str(remaining),
                    ),
                    control,
                )
                if result == b"ready":
                    break
                if result != b"waiting":
                    raise ValueError("Malformed recovered frontend health reply")
                control.wait(0.25)
            # As in initial service startup, a returned Popen does not yet imply
            # that apptainer has created its namespace init. Health precedes pin;
            # the original group owns both launches throughout this interval.
            for name in ("php-restored", "nginx-restored"):
                pin = NativeNamespaceIdentity.model_validate(
                    self.services.pin_namespace(name, control)
                )
                if pin.service != name:
                    raise ValueError("Recovery returned another namespace identity")
                self.pins.append(pin)
            self.result = AdminFrontendRecovered(
                stopped=self.stopped,
                state_restored_sha256=hashlib.sha256(
                    self.restored.model_dump_json().encode()
                ).hexdigest(),
                before_start=drained,
                namespaces=(self.pins[1], self.pins[0]),
                backend_ready=True,
                frontend_ready=True,
            )
            control.checkpoint()
            return self.result
        except BaseException as error:
            setattr(
                error, "admin_frontend_recovery_attempted", tuple(self.start_attempted)
            )
            setattr(error, "admin_frontend_recovery_launched", tuple(self.launched))
            setattr(error, "admin_frontend_recovery_pins", tuple(self.pins))
            setattr(error, "admin_frontend_recovered", self.result)
            # The same original owner always closes the whole retained group,
            # including children whose start acknowledgement was interrupted.
            raise
