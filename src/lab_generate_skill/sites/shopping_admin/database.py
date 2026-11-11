"""Native DB leaf for a pre-registered, supervised, private Admin instance.

Asset pins, canonical local paths and instance ownership must be verified by
its resource owner before use. This component performs no service start, HTTP,
Redis/media reset, admission or cleanup/deletion of partial snapshots.
"""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .database_contract import (
    AdminDatabaseLayout,
    AdminDatabaseSnapshot,
    DatabaseReply,
    DatabaseReplyError,
)
from .database_script import DATABASE_SNAPSHOT_PHP


def database_argv(layout: AdminDatabaseLayout, *arguments: str) -> tuple[str, ...]:
    layout = AdminDatabaseLayout.model_validate(layout)
    return (
        layout.apptainer,
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/",
        "--bind",
        layout.state_root + ":/state",
        layout.image_path,
        "php",
        "-r",
        DATABASE_SNAPSHOT_PHP,
        *arguments,
    )


class AdminDatabase:
    def __init__(self, layout: AdminDatabaseLayout, commands: NativeCommands) -> None:
        self.layout = AdminDatabaseLayout.model_validate(layout)
        self.commands = commands

    def _call(
        self,
        operation: str,
        control: OperationControl,
        baseline: AdminDatabaseSnapshot | None = None,
    ) -> DatabaseReply:
        control.checkpoint()
        arguments = (
            (operation,)
            if baseline is None
            else (operation, baseline.sha256, str(baseline.size_bytes))
        )
        raw = self.commands.run(database_argv(self.layout, *arguments), control)
        try:
            reply = DatabaseReply.model_validate_json(raw)
            if (
                raw != reply.model_dump_json().encode()
                or reply.operation != operation
                or (
                    baseline is not None
                    and (reply.sha256, reply.size_bytes)
                    != (baseline.sha256, baseline.size_bytes)
                )
            ):
                raise ValueError(
                    "Native reply differs from requested original baseline"
                )
            return reply
        except (ValueError, TypeError) as error:
            raise DatabaseReplyError(raw) from error

    def save(self, control: OperationControl) -> AdminDatabaseSnapshot:
        reply = self._call("save", control)
        return AdminDatabaseSnapshot(
            layout=self.layout, size_bytes=reply.size_bytes, sha256=reply.sha256
        )

    def verify(
        self, baseline: AdminDatabaseSnapshot, control: OperationControl
    ) -> DatabaseReply:
        """Read/verify original held snapshot; never starts a database client."""
        baseline = AdminDatabaseSnapshot.model_validate(baseline)
        if baseline.layout != self.layout:
            raise ValueError("Verify must use the original instance and staged image")
        return self._call("verify", control, baseline)

    def restore(
        self, baseline: AdminDatabaseSnapshot, control: OperationControl
    ) -> DatabaseReply:
        baseline = AdminDatabaseSnapshot.model_validate(baseline)
        if baseline.layout != self.layout:
            raise ValueError("Restore must use the original instance and staged image")
        return self._call("restore", control, baseline)
