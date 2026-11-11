"""Observe original SQL/Redis/search after frontends stop under one deadline.

Only valid busy observations may be polled. Command/protocol errors stop at once;
there are no mutation retries, alternate endpoints or environment-selected ports.
"""

import json
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import AdminServiceSpec
from .service_commands import container
from .frontend_contract import AdminBackendDrain
from .drain_program import DATABASE_DRAIN_PHP, SEARCH_DRAIN_PHP


def redis_clients(raw: bytes) -> tuple[int, int]:
    fields: dict[str, str] = {}
    text = raw.decode("ascii")
    if not text.startswith("# Clients\r\n") or not text.endswith("\r\n"):
        raise ValueError("Incomplete Redis clients reply")
    for line in text.splitlines()[1:]:
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep or key in fields:
            raise ValueError("Malformed Redis clients reply")
        fields[key] = value
    values = tuple(fields.get(k, "") for k in ("connected_clients", "blocked_clients"))
    if any(not v.isdecimal() or len(v) > 10 for v in values):
        raise ValueError("Missing Redis activity counts")
    return int(values[0]), int(values[1])


class AdminDrain:
    def __init__(self, service: AdminServiceSpec, commands: NativeCommands) -> None:
        self.service = AdminServiceSpec.model_validate(service)
        self.commands = commands
        self.last: AdminBackendDrain | None = None

    def wait(self, control: OperationControl) -> AdminBackendDrain:
        base = container(self.service)
        try:
            while True:
                control.checkpoint()
                sql = json.loads(
                    self.commands.run(base + ("php", "-r", DATABASE_DRAIN_PHP), control)
                )
                if not isinstance(sql, dict) or set(sql) != {
                    "other_sql_connections",
                    "sql_transactions",
                }:
                    raise ValueError("Invalid DB activity reply")
                clients, blocked = redis_clients(
                    self.commands.run(
                        base
                        + (
                            "redis-cli",
                            "--raw",
                            "-h",
                            "127.0.0.1",
                            "-p",
                            str(self.service.ports.redis),
                            "INFO",
                            "clients",
                        ),
                        control,
                    )
                )
                remaining = control.checkpoint()
                search = json.loads(
                    self.commands.run(
                        base
                        + (
                            "php",
                            "-r",
                            SEARCH_DRAIN_PHP,
                            str(self.service.ports.search),
                            str(remaining),
                        ),
                        control,
                    )
                )
                if not isinstance(search, dict) or set(search) != {
                    "search_write_tasks"
                }:
                    raise ValueError("Invalid search activity reply")
                self.last = AdminBackendDrain(
                    **sql, redis_clients=clients, redis_blocked=blocked, **search
                )
                control.checkpoint()
                if self.last.drained:
                    return self.last
                control.wait(0.05)
        except BaseException as error:
            setattr(error, "admin_backend_drain", self.last)
            raise
