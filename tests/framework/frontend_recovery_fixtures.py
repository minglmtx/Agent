"""Synthetic backend/namespace ownership; actual files for composed state records."""

from pathlib import Path
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.frontend_contract import (
    AdminFrontendStopped,
)
from lab_generate_skill.sites.shopping_admin.state_contract import AdminStateRestored
from lab_generate_skill.sites.shopping_admin.frontend_recovery import (
    AdminFrontendRecovery,
)
from lab_generate_skill.sites.shopping_admin.service_programs import HEALTH
from test_admin_frontend import Commands as DrainCommands
from test_admin_services import Services
from test_admin_state import state
from frontend_fixtures import frontend, namespace
from test_slurm_commands import guard


class Commands(DrainCommands):
    def __init__(self) -> None:
        super().__init__()
        self.health = {"backend": [b"ready"], "frontend": [b"ready"]}
        self.configuration_failure: str | None = None

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        if HEALTH in argv:
            phase = argv[argv.index(HEALTH) + 1]
            self.calls.append("health:" + phase)
            values = self.health[phase]
            return values.pop(0) if len(values) > 1 else values[0]
        if "nginx" in argv or "php-fpm" in argv:
            name = "nginx" if "nginx" in argv else "php"
            self.calls.append("config:" + name)
            if name == self.configuration_failure:
                raise OSError("bad original " + name + " configuration")
            return b""
        return super().run(argv, control)


def recovered_namespace(name: str) -> NativeNamespaceIdentity:
    original = namespace(name.removesuffix("-restored"))
    return original.model_copy(
        update={
            "service": name,
            "launcher": original.launcher.model_copy(
                update={"process_id": original.launcher.process_id + 1000}
            ),
            "init": original.init.model_copy(
                update={"process_id": original.init.process_id + 1000}
            ),
            "namespace_inode": original.namespace_inode + 1000,
        }
    )


class Group(Services):
    def __init__(self) -> None:
        super().__init__()
        self.names = ["mysql", "redis", "search", "php", "nginx"]
        self.pin_failure: str | None = None

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        control.checkpoint()
        self.pins.append(name)
        if name == self.pin_failure:
            raise OSError("new original namespace pin failed")
        return recovered_namespace(name)


class Authority:
    def __init__(
        self, stopped: AdminFrontendStopped, restored: AdminStateRestored
    ) -> None:
        self.stopped, self.restored, self.denied = stopped, restored, False
        self.calls = 0

    def verify(
        self,
        stopped: AdminFrontendStopped,
        restored: AdminStateRestored,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        assert (stopped, restored) == (self.stopped, self.restored)
        if self.denied:
            raise PermissionError("Recovery not authorized")


def fixture(root: Path) -> tuple[AdminFrontendRecovery, Commands, Group, Authority]:
    worker, _, _ = state(root)
    saved = worker.save(guard())
    restored = worker.restore(saved, guard())
    stopped = frontend(worker.plan.service)
    commands, group = Commands(), Group()
    authority = Authority(stopped, restored)
    recovery = AdminFrontendRecovery(
        stopped, restored, commands=commands, services=group, authority=authority
    )
    return recovery, commands, group, authority
