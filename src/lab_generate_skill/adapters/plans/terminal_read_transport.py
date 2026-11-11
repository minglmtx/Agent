"""One protected terminal proof in the original ready namespace; no native effects."""

import hashlib
import os
import threading
from contextlib import contextmanager
from collections.abc import Iterator
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    require_reaped,
    retained_capture,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.adapters.storage.installation_receipt import (
    check_storage_installation,
)
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.domain.terminal_read import (
    TerminalReadRequest,
    TerminalReadCommand,
    TerminalReadBodies,
)
from lab_generate_skill.ports.evidence_storage import EvidenceStorageAdmission
from lab_generate_skill.ports.lifecycle import OperationControl
from .terminal_read_protocol import ENTRY, MAX_PACKET, TerminalReadReply, encode_command


class TerminalReadFailure(EvidenceError):
    def __init__(
        self, capture: CommandCapture | None, reply: TerminalReadReply | None
    ) -> None:
        self.capture, self.reply = capture, reply
        super().__init__(
            "Original readonly terminal proof unconfirmed; retain child facts"
        )


class SupervisedTerminalReads:
    def __init__(
        self,
        scope: OwnerMetadataStorageScope,
        store: ManagedEvidenceStore,
        admission: EvidenceStorageAdmission,
        task: TaskIdentity,
    ) -> None:
        self.scope = OwnerMetadataStorageScope.model_validate(scope)
        self.task = TaskIdentity.model_validate(task)
        if not isinstance(store, ManagedEvidenceStore) or admission is None:
            raise TypeError("Original ready store and real storage admission required")
        if self.scope.binding.source_task_id not in (None, self.task.source_task_id):
            raise OwnershipConflict("Terminal reader changed original source task")
        self.store, self.admission = store, admission
        self.runner = ProcessRunner(max_output_bytes=MAX_PACKET)
        self.owner_context = os.getpid(), threading.get_ident()
        self.quarantined = False
        self.last_capture: CommandCapture | None = None
        self.last_reply: TerminalReadReply | None = None
        self.last_request: bytes | None = None

    @contextmanager
    def _original(
        self, control: OperationControl
    ) -> Iterator[tuple[EvidenceReadScope, OperationControl]]:
        if self.owner_context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Terminal reader left original controller/thread")
        if self.quarantined:
            raise TerminalReadFailure(self.last_capture, self.last_reply)
        control.checkpoint()
        with self.store.read_scope(control) as (read, bounded):
            if (read.binding, read.config, read.controller) != (
                self.scope.binding,
                self.scope.config,
                self.scope.writer,
            ) or current_process_identity() != read.controller:
                raise OwnershipConflict(
                    "Terminal proof changed original metadata owner/store"
                )
            yield read, bounded

    def check_current(self, control: OperationControl) -> None:
        with self._original(control) as (read, bounded):
            self.admission.authorize_storage(
                read.binding, read.config, read.operation, bounded
            )
            after = read.operation.model_copy(
                update={"operation_id": read.operation.operation_id + ".after"}
            )
            self.admission.authorize_storage(read.binding, read.config, after, bounded)
            bounded.checkpoint()

    def read(
        self, request: TerminalReadRequest, control: OperationControl
    ) -> TerminalReadBodies:
        request = TerminalReadRequest.model_validate(request)
        if request.initial.prepared.scope.task != self.task:
            raise OwnershipConflict("Terminal proof changed selected original task")
        self.last_capture, self.last_reply, self.last_request = None, None, None
        with self._original(control) as (read, bounded):
            command = TerminalReadCommand(
                scope=read, workspace_root=self.scope.workspace_root, request=request
            )
            packet = encode_command(command)
            self.last_request = packet
            self.admission.authorize_storage(
                read.binding, read.config, read.operation, bounded
            )
            capture: CommandCapture | None = None
            try:
                capture = self.runner.run(
                    (
                        read.config.installation.python_executable,
                        "-I",
                        "-B",
                        "-m",
                        ENTRY,
                    ),
                    bounded,
                    stdin_bytes=packet,
                )
                self.last_capture = capture
                ending = require_reaped(capture)
                if (
                    not capture.complete
                    or capture.returncode != 0
                    or not 0 < len(capture.stdout) <= MAX_PACKET
                ):
                    raise TerminalReadFailure(capture, None)
                reply = TerminalReadReply.model_validate_json(capture.stdout)
                self.last_reply = reply
                if (
                    reply.request_sha256 != hashlib.sha256(packet).hexdigest()
                    or reply.worker.process_id != ending.process_id
                ):
                    raise OwnershipConflict(
                        "Terminal reply changed original child/request"
                    )
                if reply.error is not None:
                    raise TerminalReadFailure(capture, reply)
                check_storage_installation(
                    read.config,
                    reply.installed_sources,
                    entry_module=ENTRY,
                    required=True,
                )
                if (
                    reply.bodies is None
                    or reply.bodies.request != request
                    or reply.bodies.purpose != "same_task"
                ):
                    raise OwnershipConflict(
                        "Terminal proof changed requested complete inputs"
                    )
                after = read.operation.model_copy(
                    update={"operation_id": read.operation.operation_id + ".after"}
                )
                self.admission.authorize_storage(
                    read.binding, read.config, after, bounded
                )
                bounded.checkpoint()
                return reply.bodies
            except BaseException as error:
                known = capture or retained_capture(error)
                if known is not None:
                    self.last_capture = known
                if (
                    known is None
                    or known.termination is None
                    or known.termination.state != "reaped"
                ):
                    self.quarantined = True
                raise
