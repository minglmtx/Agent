"""Single-child ordered model service; injected factory, no launch or task rights.

A wire sequence is consumed before engine effects. Repeating/skipping/changing
session identity is fatal. Business-request deduplication remains the durable
inference ledger's responsibility; a new sequence is not proof of admission.
"""

from collections.abc import Callable
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.local_generator import LocalGeneratorOutput
from lab_generate_skill.domain.generator_model import MAX_GENERATOR_RESPONSE_BYTES
from lab_generate_skill.domain.generator_engine import GeneratorEngineConfig
from lab_generate_skill.domain.generator_installation import (
    GeneratorInstallation,
    GeneratorInstalledSources,
)
from lab_generate_skill.domain.errors import (
    GeneratorInputBudgetExceeded,
    OwnershipConflict,
)
from lab_generate_skill.ports.local_generator import ManagedLocalGeneratorEngine
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .generator_worker_protocol import (
    GeneratorWorkerCommand,
    GeneratorWorkerReply,
    validate_worker_output,
)

EngineFactory = Callable[
    [ReleaseArtifact, GeneratorEngineConfig], ManagedLocalGeneratorEngine
]


class GeneratorService:
    def __init__(
        self,
        factory: EngineFactory,
        installation_verifier: Callable[
            [GeneratorInstallation, OperationControl], GeneratorInstalledSources
        ],
        guard_verifier: Callable[
            [ProcessIdentity, OperationControl], ProcessOwnerGuard
        ],
    ) -> None:
        self._guard_verifier = guard_verifier
        self._factory = factory
        self._installation_verifier = installation_verifier
        self._engine: ManagedLocalGeneratorEngine | None = None
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

    def handle(self, command: GeneratorWorkerCommand) -> GeneratorWorkerReply:
        command = GeneratorWorkerCommand.model_validate(command)
        status = "ok"
        output = None
        error = None
        worker = None
        installed_sources = None
        owner_guard = None
        try:
            if (
                self._closed
                or command.sequence != self._sequence + 1
                or (self._session is not None and command.session_id != self._session)
            ):
                raise OwnershipConflict("Generator worker session/sequence is not next")
            self._sequence = command.sequence
            self._session = command.session_id
            control = DeadlineControl(
                command.remaining_seconds, f"worker-{command.sequence}"
            )
            control.checkpoint()
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
                installed_sources = GeneratorInstalledSources.model_validate(
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
                        output = validate_worker_output(
                            self._engine.generate(
                                command.request, command.parameters, control
                            ),
                            command.parameters,
                        )
                        if (
                            len(output.model_dump_json().encode())
                            > MAX_GENERATOR_RESPONSE_BYTES
                        ):
                            raise ValueError("Generator output exceeds response budget")
            control.checkpoint()
        except BaseException as primary:
            if isinstance(
                primary, GeneratorInputBudgetExceeded
            ) and command.operation in ("validate", "generate"):
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
                        "Generator service and cleanup failed", [primary, cleanup]
                    )
                error = describe_error(primary)
        return GeneratorWorkerReply.model_validate(
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
