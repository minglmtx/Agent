"""Original native service generation, separate from resource ownership."""

from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from typing import Literal
from pathlib import Path
from .service_contract import GitlabServiceSpec
from .service_commands import container, service_commands, SERVICE_NAMES, RUBY
from .service_programs import (
    SEED,
    CONFIGURE,
    SERVICE_WRAPPER,
    POSTGRES_READY,
    BACKEND_READY,
    HTTP_READY,
)
from .service_files import write_controls, checked
from .progress import GitlabPhase, GitlabProgress
from .shutdown_contract import GitalyTermExit
from .shutdown_log import read_workhorse_term_exit
from .workhorse_shutdown import WorkhorseTermExit


def seed(
    spec: GitlabServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    base = container(spec, seeded=False)
    state = Path(spec.files.state_root)
    checked(state, control)
    if not state.is_dir() or any(state.iterdir()):
        raise ValueError("Fresh original GitLab state required before native commands")
    write_controls(spec, control)
    # This pinned image's dash executes -n -c command strings. Check named
    # immutable files instead, and prove noexec with a harmless sentinel first.
    for name in ("noexec-check.sh", "seed.sh", "postgres-ready.sh"):
        if commands.run(base + ("/bin/sh", "-n", "/control/" + name), control) != b"":
            raise ValueError("Native shell syntax check unexpectedly executed code")
    if commands.run(base + ("/bin/bash", "-n", "/control/service.sh"), control) != b"":
        raise ValueError("Native wrapper syntax check returned unexpected output")
    for program in (CONFIGURE, BACKEND_READY, HTTP_READY):
        if commands.run(base + (RUBY, "-c", "-e", program), control) != b"Syntax OK\n":
            raise ValueError("Native Ruby syntax check did not confirm compilation")
    control.checkpoint()
    if any(state.iterdir()):
        raise ValueError("Native syntax preflight changed the original empty state")
    commands.run(base + ("/bin/sh", "-e", "/control/seed.sh"), control)
    raw = commands.run(
        base
        + (
            RUBY,
            "-e",
            CONFIGURE,
            str(spec.ports.web),
            str(spec.ports.metrics),
            spec.database_peer_user,
        ),
        control,
    )
    if raw != b"configured":
        raise ValueError("Incomplete original native GitLab configuration")


def require_stop(
    stopped: NativeServiceQuiescence,
    pins: tuple[NativeNamespaceIdentity, ...],
    gitaly_term: GitalyTermExit | None = None,
    workhorse_terms: tuple[WorkhorseTermExit, ...] = (),
) -> None:
    stopped = NativeServiceQuiescence.model_validate_json(stopped.model_dump_json())
    if (
        tuple(x.service for x in stopped.masters) != SERVICE_NAMES
        or tuple(x.original for x in stopped.namespaces) != pins
    ):
        raise ValueError("Every original GitLab service pin must be stopped")
    if len(workhorse_terms) > 2 or len(
        {p.original.service for p in workhorse_terms}
    ) != len(workhorse_terms):
        raise ValueError("Distinct original Workhorse shutdown proofs required")
    workhorse = {
        p.original.service: WorkhorseTermExit.model_validate_json(p.model_dump_json())
        for p in workhorse_terms
    }
    if gitaly_term is not None:
        raise ValueError("Gitaly child exit log cannot authorize a wrapper exit")
    for master in stopped.masters:
        allowed = (
            (0,) if master.service in ("postgres", "redis", "gitaly") else (0, -15, 143)
        )
        if (
            master.service in ("workhorse", "workhorse-internal")
            and master.returncode == 1
        ):
            completion = workhorse.get(master.service)
            if completion is None or completion.original != next(
                p for p in pins if p.service == master.service
            ):
                raise ValueError("Workhorse exit1 requires original10s TERM/nil proof")
            allowed = (1,)
        if master.returncode not in allowed:
            raise ValueError("Abnormal native stop cannot authorize GitLab snapshot")
    if any(
        next(m for m in stopped.masters if m.service == name).returncode != 1
        for name in workhorse
    ):
        raise ValueError("Workhorse proof changed original exit code")


class GitlabGeneration:
    def __init__(
        self,
        spec: GitlabServiceSpec,
        commands: NativeCommands,
        services: QuiescentNativeServices,
        *,
        progress: GitlabProgress | None = None,
        log_root: Path | None = None,
    ) -> None:
        self.spec = GitlabServiceSpec.model_validate(spec)
        self.commands, self.services, self.progress = commands, services, progress
        self.state = "new"
        self.pins: tuple[NativeNamespaceIdentity, ...] = ()
        self.quiescence: NativeServiceQuiescence | None = None
        self.log_root = log_root
        self.gitaly_term: GitalyTermExit | None = None
        self.workhorse_terms: tuple[WorkhorseTermExit, ...] = ()

    def _phase(self, phase: GitlabPhase) -> None:
        if self.progress is not None:
            self.progress(phase)

    def _wait(
        self,
        phase: Literal["postgres", "backend", "frontend"],
        control: OperationControl,
    ) -> None:
        while True:
            remaining = control.checkpoint()
            self.services.require_running()
            args: tuple[str, ...]
            if phase == "postgres":
                args = ("/bin/sh", "/control/postgres-ready.sh")
            elif phase == "backend":
                args = (RUBY, "-e", BACKEND_READY, str(remaining))
            else:
                args = (
                    RUBY,
                    "-e",
                    HTTP_READY,
                    str(self.spec.ports.web),
                    str(remaining),
                )
            raw = self.commands.run(container(self.spec) + args, control)
            if raw == b"ready":
                return
            if raw != b"waiting":
                raise ValueError("Malformed native GitLab health response")
            control.wait(0.25)

    def start(self, control: OperationControl) -> str:
        if self.state != "new":
            raise RuntimeError("Original GitLab generation starts once")
        control.checkpoint()
        self.state = "starting"
        try:
            self._phase(GitlabPhase.BACKEND_BEGIN)
            argv = service_commands(self.spec)
            self.services.start("postgres", argv["postgres"], control)
            self._wait("postgres", control)
            for name in SERVICE_NAMES[1:3]:
                self.services.start(name, argv[name], control)
            self._wait("backend", control)
            self._phase(GitlabPhase.BACKEND_READY)
            self._phase(GitlabPhase.FRONTEND_BEGIN)
            for name in SERVICE_NAMES[3:]:
                self.services.start(name, argv[name], control)
            self._wait("frontend", control)
            for name in SERVICE_NAMES:
                self.pins += (self.services.pin_namespace(name, control),)
            control.checkpoint()
            self.state = "ready"
            self._phase(GitlabPhase.FRONTEND_READY)
            return self.spec.endpoint
        except BaseException:
            self.state = "failed"
            raise

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        if self.state != "ready":
            raise RuntimeError("Quiescence requires original ready GitLab generation")
        self.state = "quiescing"
        try:
            self.quiescence = self.services.quiesce(control)
            if (
                next(
                    m for m in self.quiescence.masters if m.service == "gitaly"
                ).returncode
                != 0
            ):
                raise ValueError("Original pinned Gitaly wrapper must exit0")
            for master in self.quiescence.masters:
                if (
                    master.service in ("workhorse", "workhorse-internal")
                    and master.returncode == 1
                ):
                    if self.log_root is None:
                        raise ValueError("Original Workhorse generation log required")
                    self.workhorse_terms += (
                        read_workhorse_term_exit(
                            self.log_root,
                            next(p for p in self.pins if p.service == master.service),
                            self.spec.files.image.sha256,
                            control,
                        ),
                    )
            require_stop(
                self.quiescence, self.pins, self.gitaly_term, self.workhorse_terms
            )
            self.state = "quiescent"
            return self.quiescence
        except BaseException:
            self.state = "failed"
            raise

    def confirm_healthy(self, control: OperationControl) -> str:
        if self.state != "ready":
            raise RuntimeError("Health confirmation requires original ready generation")
        self._wait("frontend", control)
        return self.spec.endpoint

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.state = "stopping"
        try:
            result = self.services.stop(control)
            self.state = "stopped"
            return result
        except BaseException:
            self.state = "failed"
            raise
