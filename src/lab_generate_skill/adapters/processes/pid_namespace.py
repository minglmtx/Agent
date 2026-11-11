"""Hold original Apptainer init via pidfd before any namespace stop.

Only a live unreaped direct Popen child in this process/thread is admissible.
No numeric-PID signalling, broad scans, alternate proc roots or restart. Killing
original namespace init terminates its contained descendants; host-side helpers,
backend requests and other resources remain separate closure responsibilities.
"""

import os
from pathlib import Path
import subprocess
import threading
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from .namespace_observation import child, direct_children, launcher as read_launcher
from .linux_pidfd import open_pidfd, kill_pidfd
from .owner_pidfd import ended, close_owned


class HeldPidNamespace:
    def __init__(
        self, service: str, launcher: subprocess.Popen[bytes], control: OperationControl
    ) -> None:
        self.owner = (os.getpid(), threading.get_ident())
        self.launcher = launcher
        self.fds: list[int] = []
        self.closed = False
        self.attempted = False
        self.stopped: NativeNamespaceStopped | None = None
        readings = KernelReadings(control)
        try:
            if launcher.poll() is not None:
                raise RuntimeError("Namespace must be pinned while launcher is alive")
            observer = read_process_identity(readings, os.getpid(), os.getuid())
            root = read_launcher(readings, launcher.pid, observer)
            root_status = readings.read(
                Path("/proc") / str(launcher.pid) / "status", 65536
            )
            if ("PPid:\t" + str(os.getpid()) + "\n").encode() not in root_status:
                raise ValueError("Launcher is not original direct owned child")
            self.launcher_fd = open_pidfd(launcher.pid)
            self.fds.append(self.launcher_fd)
            candidates = [
                child(readings, pid, root)
                for pid in direct_children(readings, launcher.pid)
            ]
            inits = [
                item
                for item in candidates
                if item.namespace_pids == (item.identity.process_id, 1)
            ]
            if len(inits) != 1:
                raise ValueError(
                    "Exactly one original direct child namespace init required"
                )
            original = inits[0]
            self.init_fd = open_pidfd(original.identity.process_id)
            self.fds.append(self.init_fd)
            ns_path = Path("/proc") / str(original.identity.process_id) / "ns/pid"
            ns_fd = os.open(ns_path, os.O_RDONLY | os.O_CLOEXEC)
            self.fds.append(ns_fd)
            stat = os.fstat(ns_fd)
            host = os.stat("/proc/self/ns/pid")
            current = os.stat(ns_path)
            if (stat.st_dev, stat.st_ino) == (host.st_dev, host.st_ino) or (
                stat.st_dev,
                stat.st_ino,
            ) != (current.st_dev, current.st_ino):
                raise ValueError("Original private PID namespace differs")
            if (
                child(readings, original.identity.process_id, root) != original
                or read_launcher(readings, launcher.pid, observer) != root
                or ended(self.launcher_fd)
                or ended(self.init_fd)
                or launcher.poll() is not None
            ):
                raise ValueError("Original namespace changed while pinning")
            self.identity = NativeNamespaceIdentity(
                service=service,
                launcher=root,
                init=original.identity,
                namespace_device=stat.st_dev,
                namespace_inode=stat.st_ino,
            )
            control.checkpoint()
        except BaseException as error:
            setattr(error, "namespace_kernel_capture", readings.capture())
            close_owned(self.fds, error)
            raise
        self.capture = readings.capture()

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()) or self.closed:
            raise RuntimeError("Namespace handle is closed or outside original owner")

    def stop(self, control: OperationControl) -> NativeNamespaceStopped:
        self._owner()
        if self.stopped is not None:
            control.checkpoint()
            return self.stopped
        if self.attempted:
            raise RuntimeError(
                "Namespace stop already attempted; original outer cleanup required"
            )
        control.checkpoint()
        self.attempted = True
        try:
            if not ended(self.init_fd):
                kill_pidfd(self.init_fd)
            while not ended(self.init_fd) or self.launcher.poll() is None:
                control.wait(0.02)
            assert self.launcher.returncode is not None
            self.stopped = NativeNamespaceStopped(
                original=self.identity,
                init_exit_observed=True,
                launcher_returncode=self.launcher.returncode,
            )
            control.checkpoint()
            return self.stopped
        except BaseException as error:
            setattr(error, "native_namespace_identity", self.identity)
            setattr(error, "native_namespace_stopped", self.stopped)
            raise

    def observe_stopped(self, control: OperationControl) -> NativeNamespaceStopped:
        """Read the original held identities after graceful stop; never signal."""
        if self.owner != (os.getpid(), threading.get_ident()) or self.closed:
            raise RuntimeError(
                "Namespace observation requires original open owner handles"
            )
        control.checkpoint()
        if self.attempted:
            raise RuntimeError(
                "Forced namespace stop cannot supply graceful quiescence"
            )
        try:
            while not ended(self.init_fd) or self.launcher.poll() is None:
                control.wait(0.02)
            assert self.launcher.returncode is not None
            self.stopped = NativeNamespaceStopped(
                original=self.identity,
                init_exit_observed=True,
                launcher_returncode=self.launcher.returncode,
            )
            control.checkpoint()
            return self.stopped
        except BaseException as error:
            setattr(error, "native_namespace_identity", self.identity)
            setattr(error, "native_namespace_stopped", self.stopped)
            raise

    def close(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("Namespace descriptor cannot leave original owner")
        if not self.closed:
            self.closed = True
            close_owned(self.fds)
