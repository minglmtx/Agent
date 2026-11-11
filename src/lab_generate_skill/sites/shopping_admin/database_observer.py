"""Prepare authorized observation on a new node-local DB and verify before UI.

Called only after the original empty private seed is populated, before services
start. The original credentials are reused; an initialization reply does not
prove the grant ran. Full visibility and idle counts must be checked afterwards.
"""

import json
from pathlib import Path
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .artifact_io import checked_path
from .service_contract import AdminServiceSpec
from .service_commands import container
from .database_observer_program import DATABASE_OBSERVER_INIT_PHP
from .drain_program import DATABASE_DRAIN_PHP


def require_private_node(spec: AdminServiceSpec, control: OperationControl) -> None:
    root = Path(spec.layout.node_root)
    if root == Path("/tmp") or not root.is_relative_to("/tmp"):
        raise ValueError(
            "Database observation authorization requires private /tmp root"
        )
    checked_path(root, control)
    if not root.is_dir():
        raise ValueError("Existing private node root required")


def prepare_observer(
    spec: AdminServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    require_private_node(spec, control)
    reply = commands.run(
        container(spec) + ("php", "-r", DATABASE_OBSERVER_INIT_PHP), control
    )
    if reply != b"observer-configured":
        raise ValueError("Database observer initialization not confirmed")


def require_initial_idle(
    spec: AdminServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    reply = json.loads(
        commands.run(container(spec) + ("php", "-r", DATABASE_DRAIN_PHP), control)
    )
    if (
        type(reply) is not dict
        or set(reply) != {"other_sql_connections", "sql_transactions"}
        or any(type(value) is not int or value != 0 for value in reply.values())
    ):
        raise ValueError("Initial database requires complete idle observation")
