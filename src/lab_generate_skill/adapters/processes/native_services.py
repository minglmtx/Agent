"""Owned foreground masters with bounded stop and private file logs.

Popen methods signal only our unreaped original children, not arbitrary PIDs or
process groups. A reaped master is NOT proof of descendant termination. Enclosing
registered CPU resource must supervise spawn/file I/O and verify its whole tree.
"""

import os
from pathlib import Path
import re
import subprocess
import threading
import time
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from .pid_namespace import HeldPidNamespace


class LocalNativeServices:
    def __init__(self, log_root: Path) -> None:
        if not log_root.is_absolute() or log_root.is_symlink() or not log_root.is_dir():
            raise ValueError("Existing private absolute log directory required")
        self.log_root = log_root
        self.owner = (os.getpid(), threading.get_ident())
        self.attempted: set[str] = set()
        self.children: dict[str, subprocess.Popen[bytes]] = {}
        self.killed: set[str] = set()
        self.stopping = False
        self.quiescing = False
        self.quiescence: NativeServiceQuiescence | None = None
        self.namespaces: dict[str, HeldPidNamespace] = {}

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("Service handles cannot leave their original owner")

    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        self._owner()
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
            raise ValueError("Invalid fixed service name")
        if (
            type(argv) is not tuple
            or not argv
            or any(type(a) is not str or "\0" in a for a in argv)
            or not os.path.isabs(argv[0])
        ):
            raise ValueError("Expected absolute executable and exact nonempty argv")
        if self.stopping or self.quiescing or name in self.attempted:
            raise RuntimeError("Service launch already attempted or group stopping")
        control.checkpoint()
        self.attempted.add(name)
        fd = os.open(
            self.log_root / (name + ".log"),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        primary: BaseException | None = None
        try:
            child = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=fd,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            )
            self.children[name] = child  # retain even if the next checkpoint fails
            control.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(fd)
            except BaseException as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Service start and log close failed", [primary, error]
                    ) from None
                raise

    def require_running(self) -> None:
        self._owner()
        if self.stopping or self.quiescing or not self.children:
            raise RuntimeError("No running service group")
        exited = {
            name: p.poll() for name, p in self.children.items() if p.poll() is not None
        }
        if exited:
            raise RuntimeError(f"Original service master exited: {exited}")

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        self._owner()
        if (
            self.stopping
            or self.quiescing
            or name in self.namespaces
            or name not in self.children
        ):
            raise RuntimeError(
                "Namespace pin requires one original live unpinned service"
            )
        held = HeldPidNamespace(name, self.children[name], control)
        self.namespaces[name] = held
        return held.identity

    def stop_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceStopped:
        self._owner()
        if self.stopping or name not in self.namespaces:
            raise RuntimeError("Namespace stop requires its original held service")
        return self.namespaces[name].stop(control)

    def observations(self) -> tuple[NativeServiceExit, ...]:
        self._owner()
        return tuple(
            NativeServiceExit(
                service=name,
                process_id=p.pid,
                returncode=p.returncode,
                state="reaped" if p.returncode is not None else "unconfirmed",
                kill_requested=name in self.killed,
            )
            for name, p in self.children.items()
        )

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        """Signal original masters once and retain namespace handles on failure.

        No grace-period fallback or force stop. This is below the registered
        resource boundary; caller must still verify its application checkpoint.
        Existing stop remains the independent cleanup path after failure.
        """
        self._owner()
        control.checkpoint()
        if (
            self.stopping
            or self.quiescing
            or not self.children
            or set(self.namespaces) != set(self.children)
        ):
            raise RuntimeError(
                "Quiescence needs every original live namespace and one attempt"
            )
        self.require_running()
        if self.killed or any(
            held.attempted or held.closed for held in self.namespaces.values()
        ):
            raise RuntimeError(
                "Forced/closed namespace cannot supply graceful quiescence"
            )
        self.quiescing = True
        errors: list[BaseException] = []
        for child in reversed(tuple(self.children.values())):
            try:
                child.terminate()
            except BaseException as error:
                errors.append(error)
        try:
            if errors:
                raise BaseExceptionGroup("Original service TERM failed", errors)
            observed = []
            for name in self.children:
                observed.append(self.namespaces[name].observe_stopped(control))
            self.quiescence = NativeServiceQuiescence(
                masters=self.observations(), namespaces=tuple(observed)
            )
            control.checkpoint()
            return self.quiescence
        except BaseException as error:
            setattr(error, "service_exits", self.observations())
            setattr(error, "native_service_quiescence", self.quiescence)
            setattr(
                error,
                "native_namespaces_stopped",
                tuple(
                    h.stopped for h in self.namespaces.values() if h.stopped is not None
                ),
            )
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._owner()
        self.stopping = True
        errors: list[BaseException] = []
        # Always attempt every original master, including partially acquired groups.
        for child in reversed(tuple(self.children.values())):
            try:
                child.terminate()
            except BaseException as error:
                errors.append(error)
        try:
            grace_end = time.monotonic() + min(5.0, control.checkpoint() / 2)
            while any(p.poll() is None for p in self.children.values()):
                control.checkpoint()
                if time.monotonic() >= grace_end:
                    for name, child in self.children.items():
                        if child.poll() is None and name not in self.killed:
                            self.killed.add(name)
                            try:
                                child.kill()
                            except BaseException as error:
                                errors.append(error)
                control.wait(0.05)
        except BaseException as error:
            errors.append(error)
            for name, child in self.children.items():
                if child.poll() is None and name not in self.killed:
                    self.killed.add(name)
                    try:
                        child.kill()
                    except BaseException as cleanup:
                        errors.append(cleanup)
        for child in self.children.values():
            child.poll()
        for held in self.namespaces.values():
            try:
                held.close()
            except BaseException as error:
                errors.append(error)
        facts = self.observations()
        if any(f.state != "reaped" for f in facts):
            errors.append(
                RuntimeError("Original service master termination unconfirmed")
            )
        if errors:
            group = BaseExceptionGroup("Native service cleanup failed", errors)
            setattr(group, "service_exits", facts)
            raise group
        return facts
