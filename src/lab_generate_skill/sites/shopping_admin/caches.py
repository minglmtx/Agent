"""Invalidate only the predeclared private Admin application's caches.

Caller must exclude all other writers and verify original service/port ownership.
Never reads environment-selected ports or falls back to another server. Commands
run once under original control; a failed or unknown mutation is not retried.
"""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import AdminServiceSpec
from .service_commands import container
from .cache_contract import AdminCacheReset


class AdminCaches:
    def __init__(self, service: AdminServiceSpec, commands: NativeCommands) -> None:
        self.service = AdminServiceSpec.model_validate(service)
        self.commands = commands

    def reset(self, control: OperationControl) -> AdminCacheReset:
        control.checkpoint()
        base = container(self.service)
        # Magento clears its filesystem/application cache before the final Redis
        # flush. INFO keyspace checks all DBs, not only default DBSIZE.
        self.commands.run(
            base + ("php", "/var/www/magento2/bin/magento", "cache:flush"), control
        )
        redis = base + (
            "redis-cli",
            "--raw",
            "-h",
            "127.0.0.1",
            "-p",
            str(self.service.ports.redis),
        )
        answer = self.commands.run(redis + ("FLUSHALL",), control)
        if answer not in (b"OK\n", b"OK\r\n"):
            raise ValueError("Original Redis flush was not acknowledged")
        keyspace = self.commands.run(redis + ("INFO", "keyspace"), control)
        # Reject errors, malformed/truncated headers and any remaining database.
        if keyspace.replace(b"\r\n", b"\n").strip(b"\n") != b"# Keyspace":
            raise ValueError("Original Redis keyspace is not confirmed empty")
        control.checkpoint()
        return AdminCacheReset(
            service=self.service,
            application_cache_command_succeeded=True,
            redis_all_databases_empty=True,
        )
