"""Save/verify/restore once on original private search; failures quarantine.

The fixed program performs no retry and never changes endpoint or baseline.
API completion includes shard failures, so strict completion and original index
inventory are separately checked. This is not whole-site/writer closure proof.
"""

import json
from typing import Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import AdminServiceSpec
from .service_commands import container
from .search_contract import AdminSearchSnapshot, AdminSearchRestored
from .search_authority import AdminSearchAuthority
from .search_program import SEARCH_SNAPSHOT_PHP
from .search_reply import SearchReply


class AdminSearch:
    def __init__(
        self,
        service: AdminServiceSpec,
        commands: NativeCommands,
        authority: AdminSearchAuthority,
    ) -> None:
        self.service = AdminServiceSpec.model_validate(service)
        self.commands, self.authority = commands, authority
        self.saved: AdminSearchSnapshot | None = None
        self.busy = False
        self.quarantined = False
        self.save_attempted = False
        self.restore_attempted = False

    def _call(
        self,
        phase: Literal["save", "verify", "preflight", "restore"],
        snapshot: AdminSearchSnapshot | None,
        control: OperationControl,
    ) -> SearchReply:
        if self.busy or self.quarantined:
            raise RuntimeError("Original search busy or quarantined")
        if phase != "save":
            snapshot = AdminSearchSnapshot.model_validate(snapshot)
            if snapshot.service != self.service:
                raise ValueError("Search snapshot changed original service")
        if phase == "save" and self.save_attempted:
            raise RuntimeError("Search save already attempted")
        if phase == "restore" and self.restore_attempted:
            raise RuntimeError("Search restore already attempted")
        control.checkpoint()
        self.busy = True
        attempted = False
        try:
            self.authority.verify(self.service, phase, snapshot, control)
            remaining = control.checkpoint()
            expected = (
                None
                if snapshot is None
                else snapshot.model_dump(
                    mode="json", exclude={"schema_version", "service"}
                )
            )
            if phase == "save":
                self.save_attempted = True
            if phase == "restore":
                self.restore_attempted = True
            attempted = True
            raw = self.commands.run(
                container(self.service)
                + (
                    "php",
                    "-r",
                    SEARCH_SNAPSHOT_PHP,
                    str(self.service.ports.search),
                    str(remaining),
                    phase,
                    json.dumps(expected, separators=(",", ":")),
                ),
                control,
            )
            reply = SearchReply.model_validate_json(raw)
            if raw != reply.model_dump_json(exclude_none=True).encode():
                raise ValueError("Noncanonical search reply")
            if reply.operation != phase:
                raise ValueError("Search reply changed original operation")
            observed = AdminSearchSnapshot(
                service=self.service, **reply.snapshot.model_dump()
            )
            if snapshot is not None and observed != snapshot:
                raise ValueError("Search changed original snapshot")
            if phase == "save":
                self.saved = observed
            if phase == "restore":
                if reply.health is None or reply.successful_shards != observed.shards:
                    raise ValueError("Search restoration not fully confirmed")
            elif reply.health is not None or reply.successful_shards is not None:
                raise ValueError("Read/save reply invented restored facts")
            control.checkpoint()
            return reply
        except BaseException as error:
            if attempted:
                self.quarantined = True
            setattr(error, "admin_search_snapshot", self.saved or snapshot)
            setattr(error, "admin_search_phase", phase)
            setattr(error, "admin_search_operation_started", attempted)
            raise
        finally:
            self.busy = False

    def save(self, control: OperationControl) -> AdminSearchSnapshot:
        self._call("save", None, control)
        assert self.saved is not None
        return self.saved

    def verify(self, snapshot: AdminSearchSnapshot, control: OperationControl) -> None:
        self._call("verify", snapshot, control)

    def preflight_restore(
        self, snapshot: AdminSearchSnapshot, control: OperationControl
    ) -> None:
        """Read original snapshot and current ILM/index/stream inventory, no mutation."""
        self._call("preflight", snapshot, control)

    def restore(
        self, snapshot: AdminSearchSnapshot, control: OperationControl
    ) -> AdminSearchRestored:
        reply = self._call("restore", snapshot, control)
        assert reply.health is not None and reply.successful_shards is not None
        return AdminSearchRestored(
            original=snapshot,
            restored_indices=reply.snapshot.indices,
            restored_data_streams=reply.snapshot.data_streams,
            successful_shards=reply.successful_shards,
            health=reply.health,
        )
