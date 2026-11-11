"""Single-use original SFT service. Configure has no data/model/output effects."""

from collections.abc import Callable
from datetime import datetime, timezone
from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.training_worker import TrainingWorkerBackend
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .worker_protocol import TrainingWorkerCommand, TrainingWorkerReply
from .native_execution import NativeReturnCommitUnconfirmed


class TrainingWorkerService:
    def __init__(
        self,
        factory: Callable[
            [TrainingWorkerConfiguration, ProcessOwnerGuard], TrainingWorkerBackend
        ],
        installation_verifier: Callable[
            [ReleaseInstallation, OperationControl], InstalledReleaseSources
        ],
        guard_verifier: Callable[
            [ProcessIdentity, OperationControl], ProcessOwnerGuard
        ],
    ) -> None:
        self.factory, self.installation_verifier, self.guard_verifier = (
            factory,
            installation_verifier,
            guard_verifier,
        )
        self.backend: TrainingWorkerBackend | None = None
        self.session: str | None = None
        self.sequence = 0
        self._closed = False
        self.original_deadline: datetime | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True
        backend, self.backend = self.backend, None
        if backend is not None:
            backend.close(DeadlineControl(10, "sft-worker-close"))

    def handle(self, command: TrainingWorkerCommand) -> TrainingWorkerReply:
        command = TrainingWorkerCommand.model_validate(command)
        guard = None
        installed = None
        execution_ref = None
        error = None
        status = "ok"
        try:
            if (
                self.closed
                or command.sequence != self.sequence + 1
                or (self.session is not None and command.session_id != self.session)
            ):
                raise OwnershipConflict(
                    "Training session/sequence is not next; no replay"
                )
            # Consume before effects: failures and unknown never permit train again.
            self.session, self.sequence = command.session_id, command.sequence
            control = DeadlineControl(
                command.remaining_seconds, f"sft-worker-{command.sequence}"
            )
            control.checkpoint()
            if command.operation == "configure":
                assert (
                    command.controller is not None and command.configuration is not None
                )
                guard = ProcessOwnerGuard.model_validate(
                    self.guard_verifier(command.controller, control)
                )
                if guard.controller != command.controller:
                    raise OwnershipConflict("Training guard changed controller")
                expected = command.configuration.installation
                installed = InstalledReleaseSources.model_validate(
                    self.installation_verifier(expected, control)
                )
                if (
                    installed.release_id,
                    installed.manifest_sha256,
                    installed.executable,
                ) != (
                    expected.manifest.release_id,
                    expected.manifest_ref.sha256,
                    expected.python_executable,
                ):
                    raise OwnershipConflict("Training installed release changed")
                control.checkpoint()
                self.backend = self.factory(command.configuration, guard)
                self.original_deadline = (
                    command.configuration.output.training.dataset.operation.deadline
                )
            else:
                if self.backend is None:
                    raise OwnershipConflict("Training requires configuration first")
                if command.operation == "train":
                    assert command.contract_sha256 is not None
                    assert self.original_deadline is not None
                    # Frozen wire TTL cannot renew the original execution while
                    # process/resource setup consumes its wall-clock deadline.
                    available = (
                        self.original_deadline - datetime.now(timezone.utc)
                    ).total_seconds()
                    control = DeadlineControl(
                        min(command.remaining_seconds, available),
                        "sft-original-execution",
                    )
                    control.checkpoint()
                    execution_ref = self.backend.execute(
                        command.contract_sha256, control
                    )
                else:
                    self.close()
            control.checkpoint()
        except BaseException as primary:
            status, guard, installed = "error", None, None
            if isinstance(primary, NativeReturnCommitUnconfirmed):
                execution_ref = primary.reference
            try:
                self.close()
            except BaseException as cleanup:
                primary = BaseExceptionGroup(
                    "Original SFT and child cleanup failed", [primary, cleanup]
                )
            error = describe_error(primary)
        return TrainingWorkerReply.model_validate(
            dict(
                session_id=command.session_id,
                sequence=command.sequence,
                operation=command.operation,
                command_sha256=command.digest,
                status=status,
                guard=guard,
                installed=installed,
                execution_ref=execution_ref,
                error=error,
            )
        )
