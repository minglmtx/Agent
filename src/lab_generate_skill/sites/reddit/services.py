"""One-use original native generation, beneath registered resource ownership."""

from pathlib import Path
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from .service_contract import RedditServiceSpec
from .media_initialization import initialize_media
from .media_initialization_contract import MediaInitialization
from .media_initialization_program import INITIALIZE_MEDIA
from .progress import RedditPhase, RedditProgress
from .service_commands import SERVICE_NAMES, container, service_commands
from .service_files import checked, write_controls
from .service_programs import SEED, CONFIGURE, POSTGRES_READY, TRUST_ACCOUNT, HTTP_READY


def preflight(
    spec: RedditServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    base = container(spec, seeded=False)
    for program in [SEED, POSTGRES_READY]:
        commands.run(base + ("/bin/sh", "-n", "-c", program), control)
    for program in [CONFIGURE, HTTP_READY, INITIALIZE_MEDIA]:
        commands.run(
            base + ("/usr/local/bin/php", "-r", "if(false){" + program + "}"), control
        )


def seed(
    spec: RedditServiceSpec, commands: NativeCommands, control: OperationControl
) -> MediaInitialization:
    root = Path(spec.files.state_root)
    checked(root, control)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError("Fresh private Reddit state required")
    preflight(spec, commands, control)
    commands.run(container(spec, seeded=False) + ("/bin/sh", "-ec", SEED), control)
    raw = commands.run(
        container(spec, seeded=False)
        + ("/usr/local/bin/php", "-r", CONFIGURE, str(spec.ports.database)),
        control,
    )
    if raw != b"configured":
        raise ValueError("Incomplete native Postmill configuration")
    initialization = initialize_media(spec, commands, control)
    write_controls(spec, control)
    for argv in [
        ("/usr/local/sbin/php-fpm", "--test", "--fpm-config", "/control/php.conf"),
        (
            "/usr/sbin/nginx",
            "-t",
            "-e",
            "/runtime/nginx-error.log",
            "-c",
            "/control/nginx.conf",
        ),
    ]:
        commands.run(container(spec) + argv, control)

    return initialization


def require_stop(
    facts: NativeServiceQuiescence, pins: tuple[NativeNamespaceIdentity, ...]
) -> None:
    facts = NativeServiceQuiescence.model_validate_json(facts.model_dump_json())
    if (
        tuple(m.service for m in facts.masters) != SERVICE_NAMES
        or tuple(n.original for n in facts.namespaces) != pins
        or tuple(p.service for p in pins) != SERVICE_NAMES
        or any(m.returncode != 0 for m in facts.masters)
    ):
        raise ValueError(
            "Every original Postmill native3 service must exit normally before snapshot"
        )


class RedditGeneration:
    def __init__(
        self,
        spec: RedditServiceSpec,
        commands: NativeCommands,
        services: QuiescentNativeServices,
        *,
        progress: RedditProgress | None = None,
    ) -> None:
        self.spec = RedditServiceSpec.model_validate_json(spec.model_dump_json())
        self.commands, self.services = commands, services
        self.progress = progress
        self.state = "new"
        self.pins: tuple[NativeNamespaceIdentity, ...] = ()
        self.quiescence: NativeServiceQuiescence | None = None

    def _wait(self, stage: str, control: OperationControl) -> None:
        spec = self.spec
        while True:
            control.checkpoint()
            self.services.require_running()
            tail = (
                (
                    "/bin/sh",
                    "-c",
                    POSTGRES_READY,
                    "native-postgres-ready",
                    str(spec.ports.database),
                )
                if stage == "postgres"
                else ("/usr/local/bin/php", "-r", HTTP_READY, str(spec.ports.web))
            )
            value = self.commands.run(container(spec) + tail, control)
            if value == b"ready":
                return
            if value != b"waiting":
                raise ValueError("Malformed native Postmill health reply")
            control.wait(0.25)

    def start(self, control: OperationControl, *, initialize: bool) -> str:
        if self.state != "new" or type(initialize) is not bool:
            raise InvalidTransition("Original Postmill generation starts only once")
        control.checkpoint()
        self.state = "starting"
        try:
            if self.progress is not None:
                self.progress(RedditPhase.BACKEND_BEGIN)
            argv = service_commands(self.spec)
            self.services.start("postgres", argv["postgres"], control)
            self._wait("postgres", control)
            self.pins = (self.services.pin_namespace("postgres", control),)
            if self.progress is not None:
                self.progress(RedditPhase.BACKEND_READY)
            if initialize:
                raw = self.commands.run(
                    container(self.spec)
                    + (
                        "/usr/bin/psql",
                        "-XAtq",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-h",
                        "/runtime",
                        "-p",
                        str(self.spec.ports.database),
                        "-U",
                        "postmill",
                        "-d",
                        "postmill",
                        "-c",
                        TRUST_ACCOUNT,
                    ),
                    control,
                )
                if raw != b"trusted\n":
                    raise ValueError(
                        "Original Postmill account initialization incomplete"
                    )
            for name in SERVICE_NAMES[1:]:
                self.services.start(name, argv[name], control)
            self._wait("http", control)
            for name in SERVICE_NAMES[1:]:
                self.pins += (self.services.pin_namespace(name, control),)
            if self.progress is not None:
                self.progress(RedditPhase.FRONTEND_READY)
            self.state = "running"
            return self.spec.endpoint
        except BaseException:
            self.state = "failed"
            raise

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        if self.state != "running":
            raise InvalidTransition(
                "Only original running Postmill generation may quiesce once"
            )
        control.checkpoint()
        self.state = "quiescing"
        try:
            facts = self.services.quiesce(control)
            self.quiescence = facts
            require_stop(facts, self.pins)
            self.state = "quiescent"
            return facts
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.state = "stopping"
        try:
            result = self.services.stop(control)
            self.state = "stopped"
            return result
        except BaseException:
            self.state = "failed"
            raise
