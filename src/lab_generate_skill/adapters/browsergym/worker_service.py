"""Ordered browser service in a guarded child; no launch, CAS or task judge.

Guard and installation are verified before factory/native browser effects.
Factories are fixed bootstrap dependencies, never names from wire inputs. Parent
business authority is required by the client; this service checks its original
live delegation, not independent site permission or resource-tree cleanliness.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.browser_session import RawBrowserSession
from lab_generate_skill.ports.browser_viewport import BrowserViewportSource
from lab_generate_skill.ports.browser_capture import RawBrowserCapture
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from .worker_protocol import (
    BrowserWorkerCommand,
    BrowserWorkerReply,
    decode_reply,
    WORKER_MODULE,
)


class BrowserService:
    def __init__(
        self,
        factory: Callable[[BrowserWorkerConfiguration], RawBrowserSession],
        installation_verifier: Callable[
            [ReleaseInstallation, OperationControl], InstalledReleaseSources
        ],
        guard_verifier: Callable[
            [ProcessIdentity, OperationControl], ProcessOwnerGuard
        ],
    ) -> None:
        self.factory = factory
        self.installation_verifier = installation_verifier
        self.guard_verifier = guard_verifier
        self.engine: RawBrowserSession | None = None
        self.configuration: BrowserWorkerConfiguration | None = None
        self.controller: ProcessIdentity | None = None
        self.owner_guard: ProcessOwnerGuard | None = None
        self.session: str | None = None
        self.sequence = 0
        self.closed = False
        self.last_operation: OperationContext | None = None

    def close(self) -> None:
        self.closed = True
        if self.engine is not None and self.engine.state != "closed":
            assert self.last_operation is not None
            op = self.last_operation.cleanup(
                "browser-worker-final-close", now=datetime.now(timezone.utc), seconds=10
            )
            self.engine.close(op, control=DeadlineControl(10, op.operation_id))

    def handle(self, command: BrowserWorkerCommand) -> BrowserWorkerReply:
        command = BrowserWorkerCommand.model_validate(command)
        readout = None
        captured = None
        owner_guard = None
        installed = None
        error = None
        admission_confirmed = False
        try:
            if (
                self.closed
                or command.sequence != self.sequence + 1
                or (self.session is not None and command.session_id != self.session)
            ):
                raise OwnershipConflict(
                    "Browser command is not the next original sequence"
                )
            self.sequence = command.sequence
            self.session = command.session_id
            spec = (
                command.configuration.spec
                if command.configuration is not None
                else (
                    self.configuration.spec if self.configuration is not None else None
                )
            )
            if spec is None or (
                command.operation.run_id,
                command.operation.owner_id,
                command.operation.attempt_id,
            ) != (
                spec.scope.owner.run_id,
                spec.scope.owner.owner_id,
                spec.scope.attempt_id,
            ):
                raise OwnershipConflict("Browser command changed original scope")
            self.last_operation = command.operation
            seconds = min(
                command.remaining_seconds,
                (
                    command.operation.deadline - datetime.now(timezone.utc)
                ).total_seconds(),
            )
            control = DeadlineControl(seconds, command.operation.operation_id)
            if command.phase == "configure":
                assert (
                    command.controller is not None and command.configuration is not None
                )
                self.controller = command.controller
                self.configuration = command.configuration
                owner_guard = self.guard_verifier(self.controller, control)
                if owner_guard.controller != self.controller:
                    raise OwnershipConflict("Guard belongs to another controller")
                installed = self.installation_verifier(
                    self.configuration.installation, control
                )
                expected = self.configuration.installation
                if (
                    installed.release_id,
                    installed.manifest_sha256,
                    installed.executable,
                ) != (
                    expected.manifest.release_id,
                    expected.manifest_ref.sha256,
                    expected.python_executable,
                ):
                    raise OwnershipConflict(
                        "Installation differs from original declaration"
                    )
                if WORKER_MODULE not in {m.name for m in installed.modules}:
                    raise OwnershipConflict(
                        "Fixed browser module missing from observed installation"
                    )
                self.owner_guard = owner_guard
                admission_confirmed = True
                control.checkpoint()
            else:
                if self.configuration is None or self.controller is None:
                    raise OwnershipConflict("Browser was not configured")
                actual = self.guard_verifier(self.controller, control)
                if actual != self.owner_guard:
                    raise OwnershipConflict("Original browser process guard changed")
                if command.phase == "start":
                    self.engine = self.factory(self.configuration)
                    if self.engine.spec != self.configuration.spec:
                        raise OwnershipConflict(
                            "Factory changed the frozen browser session"
                        )
                    readout = self.engine.start(command.operation, control=control)
                elif command.phase == "close":
                    if self.engine is not None:
                        self.engine.close(command.operation, control=control)
                    self.closed = True
                elif self.engine is None:
                    raise OwnershipConflict("Browser was not initialized")
                elif command.phase == "capture":
                    if (
                        not isinstance(self.engine, RawBrowserCapture)
                        or command.capture_request is None
                    ):
                        raise OwnershipConflict(
                            "Original browser lacks declared capture capability"
                        )
                    captured = self.engine.capture_page(
                        command.capture_request, control=control
                    )
                elif command.phase == "step":
                    assert command.action is not None
                    readout = self.engine.step(
                        command.action, command.operation, control=control
                    )
            # A real return remains a fact after deadline expiry. Parent checks
            # live control and persists/isolates; do not erase the obtained value.
        except BaseException as primary:
            if (
                self.engine is not None
                and self.engine.last_readout is not None
                and self.engine.last_readout.operation == command.operation
            ):
                readout = self.engine.last_readout
            if command.phase in ("configure", "close", "capture"):
                readout = None
            if (
                command.phase == "capture"
                and isinstance(self.engine, RawBrowserCapture)
                and self.engine.last_capture is not None
                and command.capture_request is not None
                and self.engine.last_capture.request_sha256
                == command.capture_request.digest
            ):
                captured = self.engine.last_capture
            try:
                self.close()
            except BaseException as cleanup:
                primary = BaseExceptionGroup(
                    "Browser service and cleanup failed", [primary, cleanup]
                )
            error = describe_error(primary)
            # A verifier failure cannot partially assert successful installation.
            if not admission_confirmed:
                owner_guard = None
                installed = None
        viewport = (
            self.engine.viewport
            if readout is not None and isinstance(self.engine, BrowserViewportSource)
            else None
        )
        reply = BrowserWorkerReply(
            schema_version=(
                "browser-worker-reply/4"
                if viewport is not None
                else "browser-worker-reply/3"
            ),
            viewport=viewport,
            session_id=command.session_id,
            sequence=command.sequence,
            phase=command.phase,
            command_sha256=command.digest,
            error=error,
            readout=readout,
            captured=captured,
            owner_guard=owner_guard,
            installed_sources=installed,
        )
        if self.configuration is not None:
            decode_reply(
                command, self.configuration.spec, reply.model_dump_json().encode()
            )
        return reply
