"""Single-child ordered model service; injected factory, no launch or task rights.

A wire sequence is consumed before engine effects. Repeating/skipping/changing
session identity is fatal. Business-request deduplication remains the durable
inference ledger's responsibility; a new sequence is not proof of admission.
"""

from collections.abc import Callable
from typing import overload
from lab_generate_skill.domain.actor_context_count import ActorTokenCount
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.actor_prompt import MAX_ACTOR_RESPONSE_BYTES
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.errors import (
    ActorInputBudgetExceeded,
    OwnershipConflict,
)
from lab_generate_skill.ports.actor_engine import LocalActorEngine, PreparedActorEngine
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .actor_worker_protocol import (
    ActorWorkerCommand,
    ActorWorkerReply,
    validate_worker_output,
)
from .actor_count_protocol import ActorCountCommand, ActorCountReply

EngineFactory = Callable[[ReleaseArtifact, ActorEngineConfig], LocalActorEngine]


class ActorService:
    def __init__(
        self,
        factory: EngineFactory,
        installation_verifier: Callable[
            [ReleaseInstallation, OperationControl], InstalledReleaseSources
        ],
        guard_verifier: Callable[
            [ProcessIdentity, OperationControl], ProcessOwnerGuard
        ],
    ) -> None:
        self._guard_verifier = guard_verifier
        self._factory = factory
        self._installation_verifier = installation_verifier
        self._engine: LocalActorEngine | None = None
        self._session: str | None = None
        self._sequence = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True
        engine, self._engine = self._engine, None
        if engine is not None:
            engine.close(DeadlineControl(10, "worker-close"))

    def _advance(self, session: str, sequence: int, seconds: float) -> DeadlineControl:
        if (
            self._closed
            or sequence != self._sequence + 1
            or (self._session is not None and session != self._session)
        ):
            raise OwnershipConflict("Actor worker session/sequence is not next")
        self._sequence, self._session = sequence, session
        control = DeadlineControl(seconds, f"worker-{sequence}")
        control.checkpoint()
        return control

    @overload
    def handle(self, command: ActorWorkerCommand) -> ActorWorkerReply: ...

    @overload
    def handle(self, command: ActorCountCommand) -> ActorCountReply: ...

    @overload
    def handle(
        self, command: ActorWorkerCommand | ActorCountCommand
    ) -> ActorWorkerReply | ActorCountReply: ...

    def handle(
        self, command: ActorWorkerCommand | ActorCountCommand
    ) -> ActorWorkerReply | ActorCountReply:
        if isinstance(command, ActorCountCommand):
            return self._count(command)
        return self._execute(command)

    def _count(self, command: ActorCountCommand) -> ActorCountReply:
        command = ActorCountCommand.model_validate(command)
        measurement = None
        error = None
        try:
            control = self._advance(
                command.session_id, command.sequence, command.remaining_seconds
            )
            if self._engine is None:
                raise OwnershipConflict("Worker requires configuration first")
            measurement = ActorTokenCount.model_validate(
                self._engine.measure(command.request, command.parameters, control)
            )
            control.checkpoint()
        except BaseException as primary:
            measurement = None
            try:
                self.close()
            except BaseException as cleanup:
                primary = BaseExceptionGroup(
                    "Actor count and cleanup failed", [primary, cleanup]
                )
            error = describe_error(primary)
        return ActorCountReply(
            session_id=command.session_id,
            sequence=command.sequence,
            command_sha256=command.digest,
            status="ok" if error is None else "error",
            measurement=measurement,
            error=error,
        )

    def _execute(self, command: ActorWorkerCommand) -> ActorWorkerReply:
        command = ActorWorkerCommand.model_validate(command)
        status = "ok"
        output = None
        error = None
        worker = None
        installed_sources = None
        owner_guard = None
        try:
            control = self._advance(
                command.session_id, command.sequence, command.remaining_seconds
            )
            if command.operation == "configure":
                if self._engine is not None or command.sequence != 1:
                    raise OwnershipConflict("Worker config is single-use")
                assert command.artifact is not None and command.config is not None
                assert (
                    command.installation is not None and command.controller is not None
                )
                owner_guard = ProcessOwnerGuard.model_validate(
                    self._guard_verifier(command.controller, control)
                )
                if owner_guard.controller != command.controller:
                    raise OwnershipConflict(
                        "Guard verifier returned another controller"
                    )
                installed_sources = InstalledReleaseSources.model_validate(
                    self._installation_verifier(command.installation, control)
                )
                if (
                    installed_sources.release_id,
                    installed_sources.manifest_sha256,
                    installed_sources.executable,
                ) != (
                    command.installation.manifest.release_id,
                    command.installation.manifest_ref.sha256,
                    command.installation.python_executable,
                ):
                    raise OwnershipConflict(
                        "Installation verifier returned a foreign result"
                    )
                control.checkpoint()
                self._engine = self._factory(command.artifact, command.config)
                worker = owner_guard.worker
            else:
                if self._engine is None:
                    raise OwnershipConflict("Worker requires configuration first")
                if command.operation == "close":
                    self.close()
                else:
                    assert (
                        command.request is not None and command.parameters is not None
                    )
                    if command.operation == "validate":
                        self._engine.validate(
                            command.request, command.parameters, control
                        )
                    else:
                        if command.prepared_generation is not None:
                            if not isinstance(self._engine, PreparedActorEngine):
                                raise OwnershipConflict(
                                    "Selected worker lacks prepared generation; no fallback"
                                )
                            actual = self._engine.generate_prepared(
                                command.request, command.parameters, control
                            )
                        else:
                            actual = self._engine.generate(
                                command.request, command.parameters, control
                            )
                        output = validate_worker_output(
                            actual,
                            command.parameters,
                        )
                        if (
                            len(output.model_dump_json().encode())
                            > MAX_ACTOR_RESPONSE_BYTES
                        ):
                            raise ValueError("Actor output exceeds response budget")
            control.checkpoint()
        except BaseException as primary:
            if isinstance(primary, ActorInputBudgetExceeded) and command.operation in (
                "validate",
                "generate",
            ):
                # Reserved for verified pre-inference token rejection.
                status = "input_rejected"
                error = describe_error(primary)
            else:
                status = "error"
                output = None
                worker = None
                installed_sources = None
                owner_guard = None
                try:
                    self.close()
                except BaseException as cleanup:
                    primary = BaseExceptionGroup(
                        "Actor service and cleanup failed", [primary, cleanup]
                    )
                error = describe_error(primary)
        return ActorWorkerReply.model_validate(
            dict(
                session_id=command.session_id,
                sequence=command.sequence,
                operation=command.operation,
                command_sha256=command.digest,
                status=status,
                output=output,
                error=error,
                worker=worker,
                owner_guard=owner_guard,
                installed_sources=installed_sources,
            )
        )
