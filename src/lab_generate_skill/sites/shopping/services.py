"""Shopping seed and explicit service generations, below registered ownership."""

from pathlib import Path
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from .service_contract import ShoppingServiceSpec
from .service_commands import container, service_commands
from .service_programs import SEED, CONFIGURE, HEALTH, MAIL_SINK
from .static_program import NATIVE_STATIC
from .native_static import NativeStaticPublication
from .service_files import checked, write_controls
from .progress import ShoppingPhase, ShoppingProgress

SERVICE_NAMES = ("mysql", "redis", "search", "php", "nginx")


def preflight(
    spec: ShoppingServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    base = container(spec, seeded=False)
    commands.run(base + ("sh", "-n", "-c", SEED), control)
    for program in (CONFIGURE, HEALTH, MAIL_SINK, NATIVE_STATIC):
        commands.run(base + ("php", "-r", "if(false){" + program + "}"), control)


def seed(
    spec: ShoppingServiceSpec, commands: NativeCommands, control: OperationControl
) -> bytes:
    state = Path(spec.files.state_root)
    checked(state, control)
    if not state.is_dir() or any(state.iterdir()):
        raise ValueError("Fresh private Shopping state required")
    preflight(spec, commands, control)
    commands.run(container(spec, seeded=False) + ("sh", "-ec", SEED), control)
    provenance = commands.run(
        container(spec, seeded=False) + ("php", "-r", NATIVE_STATIC), control
    )
    # This exact native publisher verifies every copied digest itself. Retain
    # its raw provenance for capture/review, rather than trusting a boolean flag.
    NativeStaticPublication.model_validate_json(provenance)
    write_controls(spec, control)
    commands.run(
        container(spec)
        + (
            "nginx",
            "-t",
            "-e",
            "/runtime/nginx-error.log",
            "-c",
            "/control/nginx.conf",
        ),
        control,
    )
    commands.run(
        container(spec) + ("php-fpm", "-t", "--fpm-config", "/control/php.conf"),
        control,
    )
    return provenance


def require_consistent_stop(
    facts: NativeServiceQuiescence, pins: tuple[NativeNamespaceIdentity, ...]
) -> None:
    facts = NativeServiceQuiescence.model_validate(facts)
    if (
        tuple(x.service for x in facts.masters) != SERVICE_NAMES
        or tuple(x.original for x in facts.namespaces) != pins
    ):
        raise ValueError("Shopping stop must match every original service pin")
    for master in facts.masters:
        # JVM returns 143 after its normal TERM shutdown hook. All other native
        # masters, especially the physical MySQL writer, must return zero.
        allowed = (0, 143) if master.service == "search" else (0,)
        if master.returncode not in allowed:
            raise ValueError("Abnormal native service exit cannot authorize a snapshot")


class ShoppingGeneration:
    def __init__(
        self,
        spec: ShoppingServiceSpec,
        commands: NativeCommands,
        services: QuiescentNativeServices,
        *,
        progress: ShoppingProgress | None = None,
    ) -> None:
        self.spec = ShoppingServiceSpec.model_validate(spec)
        self.commands, self.services = commands, services
        self.progress = progress
        self.state = "new"
        self.pins: tuple[NativeNamespaceIdentity, ...] = ()
        self.quiescence: NativeServiceQuiescence | None = None

    def _phase(self, phase: ShoppingPhase) -> None:
        if self.progress is not None:
            self.progress(phase)

    def _wait(self, phase: str, control: OperationControl) -> None:
        while True:
            remaining = control.checkpoint()
            self.services.require_running()
            ports = self.spec.ports
            args = (
                (phase, str(ports.redis), str(ports.search))
                if phase == "backend"
                else (phase, str(ports.web), str(remaining))
            )
            reply = self.commands.run(
                container(self.spec) + ("php", "-r", HEALTH, *args), control
            )
            if reply == b"ready":
                return
            if reply != b"waiting":
                raise ValueError("Malformed Shopping native health reply")
            control.wait(0.25)

    def start(self, control: OperationControl, *, configure: bool) -> str:
        if self.state != "new" or type(configure) is not bool:
            raise RuntimeError("Original Shopping generation starts only once")
        control.checkpoint()
        self.state = "starting"
        try:
            self._phase(ShoppingPhase.BACKEND_BEGIN)
            argv = service_commands(self.spec)
            for name in SERVICE_NAMES[:3]:
                self.services.start(name, argv[name], control)
            self._wait("backend", control)
            self._phase(ShoppingPhase.BACKEND_READY)
            if configure:
                self._phase(ShoppingPhase.CONFIGURE_BEGIN)
                p = self.spec.ports
                raw = self.commands.run(
                    container(self.spec)
                    + (
                        "php",
                        "-r",
                        CONFIGURE,
                        str(p.database),
                        str(p.redis),
                        str(p.web),
                        str(p.search),
                    ),
                    control,
                )
                if raw != b"configured":
                    raise ValueError("Incomplete native Shopping configuration")
                for args in (
                    ("app:config:import", "--no-interaction"),
                    ("cache:flush",),
                ):
                    self.commands.run(
                        container(self.spec)
                        + ("php", "/var/www/magento2/bin/magento", *args),
                        control,
                    )
                self._phase(ShoppingPhase.CONFIGURE_READY)
            self._phase(ShoppingPhase.FRONTEND_BEGIN)
            for name in SERVICE_NAMES[3:]:
                self.services.start(name, argv[name], control)
            self._wait("frontend", control)
            # Pin only after the foreground services have reached their final
            # namespace shape. Preserve every partial pin if a later pin fails.
            for name in SERVICE_NAMES:
                self.pins += (self.services.pin_namespace(name, control),)
            control.checkpoint()
            self.state = "ready"
            self._phase(ShoppingPhase.FRONTEND_READY)
            return self.spec.endpoint
        except BaseException:
            self.state = "failed"
            raise

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        if self.state != "ready":
            raise RuntimeError("Quiescence requires this original ready generation")
        control.checkpoint()
        self.state = "quiescing"
        try:
            self.quiescence = self.services.quiesce(control)
            require_consistent_stop(self.quiescence, self.pins)
            control.checkpoint()
            self.state = "quiesced"
            return self.quiescence
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        # Resource owner still proves the enclosing domain stopped. This does
        # not release ports, remove files or promote cleanup into a safe reset.
        self.state = "stopping"
        try:
            result = self.services.stop(control)
            self.state = "stopped"
            return result
        except BaseException:
            self.state = "failed"
            raise
