"""Existing pure state checks in one fixed readonly child per fresh proof."""

import hashlib
import os
import threading
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
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.domain.state_read import StateReadCommand
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.ports.evidence_storage import EvidenceStorageAdmission
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_read_protocol import ENTRY, MAX_PACKET, StateReadReply, encode_command


class StateReadFailure(EvidenceError):
    def __init__(
        self, capture: CommandCapture | None, reply: StateReadReply | None
    ) -> None:
        self.capture, self.reply = capture, reply
        super().__init__(
            "Original readonly state proof unconfirmed; retain child facts"
        )


class SupervisedStateChecks:
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
            raise TypeError("Original ready store and live storage admission required")
        if self.scope.binding.source_task_id not in (None, self.task.source_task_id):
            raise OwnershipConflict("State reader changed its selected source task")
        self.store, self.admission = store, admission
        self.runner = ProcessRunner(max_output_bytes=MAX_PACKET)
        self.owner_context = os.getpid(), threading.get_ident()
        self.quarantined = False
        self.last_capture: CommandCapture | None = None
        self.last_reply: StateReadReply | None = None

    def _read(
        self,
        selection: EnvironmentSelection | ResetSelection,
        reference: EvidenceRef,
        operation: OperationContext | None,
        control: OperationControl,
    ) -> StateReadReply:
        if self.owner_context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("State reader left its original controller/thread")
        if self.quarantined:
            raise StateReadFailure(self.last_capture, self.last_reply)
        self.last_capture, self.last_reply = None, None
        control.checkpoint()
        with self.store.read_scope(control) as (read, bounded):
            if (read.binding, read.config, read.controller) != (
                self.scope.binding,
                self.scope.config,
                self.scope.writer,
            ) or current_process_identity() != read.controller:
                raise OwnershipConflict(
                    "State proof changed original metadata owner/store"
                )
            command = StateReadCommand(
                scope=read,
                workspace_root=self.scope.workspace_root,
                task=self.task,
                selection=selection,
                selection_ref=reference,
                operation=operation,
            )
            packet = encode_command(command)
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
                    raise StateReadFailure(capture, None)
                reply = StateReadReply.model_validate_json(capture.stdout)
                self.last_reply = reply
                if (
                    reply.request_sha256 != hashlib.sha256(packet).hexdigest()
                    or reply.worker.process_id != ending.process_id
                ):
                    raise OwnershipConflict(
                        "State reply changed original child/request"
                    )
                if reply.error is not None:
                    raise StateReadFailure(capture, reply)
                check_storage_installation(
                    read.config,
                    reply.installed_sources,
                    entry_module=ENTRY,
                    required=True,
                )
                if isinstance(selection, EnvironmentSelection):
                    result = reply.environment
                    if (
                        result is None
                        or reply.reset is not None
                        or result.scope != selection.scope
                        or result.operation != operation
                    ):
                        raise OwnershipConflict(
                            "State proof changed environment scope/operation"
                        )
                elif (
                    reply.environment is not None
                    or reply.reset is None
                    or reply.reset.plan.scope.task != self.task
                ):
                    raise OwnershipConflict("State proof changed original Reset task")
                after = read.operation.model_copy(
                    update={"operation_id": read.operation.operation_id + ".after"}
                )
                self.admission.authorize_storage(
                    read.binding, read.config, after, bounded
                )
                bounded.checkpoint()
                return reply
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

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        reply = self._read(selection, reference, operation, control)
        assert reply.environment is not None
        return reply.environment

    def reset(
        self,
        selection: ResetSelection,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> QualifiedResetChecks:
        reply = self._read(selection, reference, None, control)
        assert reply.reset is not None
        return reply.reset
