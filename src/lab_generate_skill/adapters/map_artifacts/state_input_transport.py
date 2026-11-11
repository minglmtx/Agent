"""One bounded Map input graph and final namespace check around parent semantics.

The original controller alone reads native files. Both children retain existing
installation/parent/session guards; no CAS/session write or permission cache.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import os
import threading
from lab_generate_skill.adapters.operation_progress import operation_stage
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
from lab_generate_skill.domain.map_state_inputs import MapStateInputsCommand
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.ports.evidence_storage import EvidenceStorageAdmission
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_input_protocol import ENTRY, MAX_PACKET, MapStateInputsReply, encode_command
from .state_input_bodies import MapStateBodyReader


class MapStateInputsFailure(EvidenceError):
    def __init__(
        self, capture: CommandCapture | None, reply: MapStateInputsReply | None
    ) -> None:
        self.capture, self.reply = capture, reply
        super().__init__("Original Map state input proof unconfirmed")


class MapStateInputsTransport:
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
            raise TypeError("Original ready metadata store and live admission required")
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("map", "navigation_page_identity", 1, "train"):
            raise ValueError("Original Map navigation task required")
        if self.scope.binding.source_task_id not in (None, self.task.source_task_id):
            raise OwnershipConflict("Map state inputs changed metadata source task")
        self.store, self.admission = store, admission
        self.runner = ProcessRunner(max_output_bytes=MAX_PACKET)
        self.owner = os.getpid(), threading.get_ident()
        self.quarantined = False
        self.last_capture: CommandCapture | None = None
        self.last_inputs_reply: MapStateInputsReply | None = None
        self.last_check_reply: MapStateInputsReply | None = None

    def _exchange(
        self, command: MapStateInputsCommand, control: OperationControl
    ) -> MapStateInputsReply:
        read = command.scope
        packet = encode_command(command)
        argv = (read.config.installation.python_executable, "-I", "-B", "-m", ENTRY)
        self.admission.authorize_storage(
            read.binding, read.config, read.operation, control
        )
        capture = None
        reply = None
        try:
            with operation_stage(
                "map.state-inputs"
                if command.action == "inputs"
                else "map.state-inputs-final-guard"
            ):
                capture = self.runner.run(argv, control, stdin_bytes=packet)
            self.last_capture = capture
            end = require_reaped(capture)
            if (
                not capture.complete
                or capture.returncode != 0
                or capture.stderr
                or capture.argv != argv
                or end.returncode != capture.returncode
                or not 0 < len(capture.stdout) <= MAX_PACKET
            ):
                raise MapStateInputsFailure(capture, None)
            reply = MapStateInputsReply.model_validate_json(capture.stdout)
            if (
                reply.request_sha256 != hashlib.sha256(packet).hexdigest()
                or reply.action != command.action
                or reply.worker.process_id != end.process_id
                or (reply.worker.node_id, reply.worker.boot_id)
                != (read.controller.node_id, read.controller.boot_id)
            ):
                raise OwnershipConflict(
                    "Map input reply changed original child/request"
                )
            if reply.error is not None:
                raise MapStateInputsFailure(capture, reply)
            check_storage_installation(
                read.config, reply.installed_sources, entry_module=ENTRY, required=True
            )
            control.checkpoint()
            return reply
        except BaseException as error:
            known = capture or retained_capture(error)
            self.last_capture = known
            if (
                known is None
                or known.termination is None
                or known.termination.state != "reaped"
            ):
                self.quarantined = True
            raise

    @contextmanager
    def inputs(
        self,
        selection: EnvironmentSelection | ResetSelection,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> Iterator[MapStateBodyReader]:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Map input reader left original controller/thread")
        if self.quarantined:
            raise MapStateInputsFailure(self.last_capture, self.last_inputs_reply)
        self.last_inputs_reply = self.last_check_reply = None
        with self.store.read_scope(control) as (read, bounded):
            if (read.binding, read.config, read.controller) != (
                self.scope.binding,
                self.scope.config,
                self.scope.writer,
            ) or current_process_identity() != read.controller:
                raise OwnershipConflict(
                    "Map input proof changed original metadata store"
                )
            command = MapStateInputsCommand(
                action="inputs",
                scope=read,
                workspace_root=self.scope.workspace_root,
                task=self.task,
                selection=selection,
                selection_ref=reference,
            )
            reply = self._exchange(command, bounded)
            self.last_inputs_reply = reply
            assert reply.bodies is not None
            reader = MapStateBodyReader(reply.bodies, bounded)
            try:
                yield reader
                # The parent's native-file checks happened in the original
                # controller. Recheck the exact original namespace afterwards.
                final_scope = read.model_copy(
                    update={
                        "operation": read.operation.model_copy(
                            update={
                                "operation_id": read.operation.operation_id
                                + ".map-final"
                            }
                        )
                    }
                )
                check = command.model_copy(
                    update={"action": "check", "scope": final_scope}
                )
                self.last_check_reply = self._exchange(check, bounded)
                self.admission.authorize_storage(
                    read.binding,
                    read.config,
                    read.operation.model_copy(
                        update={"operation_id": read.operation.operation_id + ".after"}
                    ),
                    bounded,
                )
                bounded.checkpoint()
            finally:
                reader.close()
