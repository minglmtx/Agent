"""Deliberately synthetic owned service handles for the new quiescence gate."""

from pathlib import Path
from typing import Any, cast
import subprocess
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.adapters.processes.pid_namespace import HeldPidNamespace
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.ports.lifecycle import OperationControl


class Child:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.terms = 0
        self.failure: BaseException | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terms += 1
        if self.failure is not None:
            raise self.failure
        self.returncode = 0

    def kill(self) -> None:
        raise AssertionError("Quiescence must not force a master")


class Held:
    def __init__(self, name: str, child: Child) -> None:
        identity = ProcessIdentity(
            node_id="unit-node",
            boot_id="00000000-0000-0000-0000-000000000001",
            process_id=child.pid,
            start_ticks=10,
        )
        self.identity = NativeNamespaceIdentity(
            service=name,
            launcher=identity,
            init=identity.model_copy(update={"process_id": child.pid + 1}),
            namespace_device=26,
            namespace_inode=child.pid,
        )
        self.attempted = False
        self.closed = False
        self.stopped: NativeNamespaceStopped | None = None
        self.failure: BaseException | None = None

    def observe_stopped(self, control: OperationControl) -> NativeNamespaceStopped:
        control.checkpoint()
        if self.failure is not None:
            raise self.failure
        self.stopped = NativeNamespaceStopped(
            original=self.identity, init_exit_observed=True, launcher_returncode=0
        )
        return self.stopped

    def close(self) -> None:
        self.closed = True


def group(root: Path) -> tuple[LocalNativeServices, dict[str, Child], dict[str, Held]]:
    services = LocalNativeServices(root)
    children = {name: Child(3100 + 100 * i) for i, name in enumerate(("mysql", "php"))}
    held = {name: Held(name, child) for name, child in children.items()}
    services.children = {
        name: cast(subprocess.Popen[bytes], child) for name, child in children.items()
    }
    services.namespaces = {
        name: cast(HeldPidNamespace, pin) for name, pin in held.items()
    }
    services.attempted = set(children)
    return services, children, held
