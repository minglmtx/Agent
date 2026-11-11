"""Retain original root-managed cgroup handles across kernel removal.

Path absence alone never suffices. Removal requires the same live-pinned inode,
original directory link marked deleted, original events FD returning ENODEV,
same host/boot/mount and ended original writer. No signals, writes or discovery.
Linux cgroup_destroy_locked refuses populated/online-child cgroups before
offlining and kernfs removal. See kernel/cgroup/cgroup.c in Linux v6.6.
"""

import errno
import os
import threading
from dataclasses import replace
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.slurm_quiescence import SlurmUserRemoval
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import close_all
from .kernel_files import _open_path, KernelControl
from .kernel_capture import KernelReadings, KernelCapture, KernelPinnedControl
from .kernel_identity import read_process_identity
from .cgroup_codec import parse_mount
from .cgroup_paths import inspect_cgroup_chain
from .cgroup_quiescence import (
    _writer_start,
    KernelQuiescenceObservation,
    observe_user_quiescence,
)


class PinnedUserTree:
    def __init__(
        self,
        original: SlurmCgroupMembership,
        fds: tuple[int, int],
        opened: KernelCapture,
        directory: KernelControl,
        events: KernelControl,
    ) -> None:
        self.original, self._fds, self.opened = original, fds, opened
        self._directory, self._events = directory, events
        self._context = (os.getpid(), threading.get_ident())
        self._closed = False

    def _owned(self) -> None:
        if self._closed or self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original cgroup handles are closed or foreign")

    def close(self) -> None:
        if self._closed:
            return
        self._owned()
        self._closed = True
        close_all(tuple(reversed(self._fds)), None)

    def removed_observation(
        self, control: OperationControl
    ) -> KernelQuiescenceObservation:
        self._owned()
        readings = KernelReadings(control)
        pins: list[KernelPinnedControl] = []
        try:
            observer = read_process_identity(readings, os.getpid(), self.original.uid)
            mount_path = Path(f"/proc/{observer.process_id}/mountinfo")
            mount = parse_mount(readings.read(mount_path, 1024 * 1024))
            if (mount.mount_id, os.makedev(mount.major, mount.minor)) != (
                self.original.mount_id,
                self.original.device,
            ):
                raise OwnershipConflict("Pinned original cgroup mount changed")
            before = _writer_start(readings, self.original)
            for _ in range(2):
                directory, events = (
                    _held(fd, expected)
                    for fd, expected in zip(self._fds, (self._directory, self._events))
                )
                links = tuple(os.readlink(f"/proc/self/fd/{fd}") for fd in self._fds)
                observed_errno = None
                try:
                    os.lseek(self._fds[1], 0, os.SEEK_SET)
                    os.read(self._fds[1], 4096)
                except OSError as error:
                    observed_errno = error.errno
                pins.append(
                    KernelPinnedControl(
                        "removed", directory, events, links[0], links[1], observed_errno
                    )
                )
                # A held kernfs event dentry can retain its original link text.
                # Original inode and ENODEV are mandatory in either link form.
                event_path = self.original.user_path + "/cgroup.events"
                if (
                    links[0] != self.original.user_path + " (deleted)"
                    or links[1] not in (event_path, event_path + " (deleted)")
                    or observed_errno != errno.ENODEV
                ):
                    raise OwnershipConflict(
                        "Original held cgroup is not proven removed"
                    )
                control.checkpoint()
            after = _writer_start(readings, self.original)
            if (
                before != after
                or parse_mount(readings.read(mount_path, 1024 * 1024)) != mount
                or read_process_identity(readings, os.getpid(), self.original.uid)
                != observer
            ):
                raise OwnershipConflict("Original removal observation changed")
            facts = SlurmUserRemoval(
                original=self.original,
                observer=observer,
                writer_status="missing" if after is None else "reused",
                replacement_start_ticks=after,
            )
            return KernelQuiescenceObservation(
                facts, replace(readings.capture(), pinned_controls=tuple(pins))
            )
        except BaseException as error:
            setattr(
                error,
                "slurm_kernel_capture",
                replace(readings.capture(), pinned_controls=tuple(pins)),
            )
            raise

    def observe(self, control: OperationControl) -> KernelQuiescenceObservation:
        self._owned()
        try:
            return observe_user_quiescence(self.original, control)
        except OSError as missing:
            if missing.errno not in (errno.ENOENT, errno.ENODEV):
                raise
            # Retain the interrupted path read as well as positive held-FD proof.
            try:
                observed = self.removed_observation(control)
            except BaseException as removal:
                raise BaseExceptionGroup(
                    "Original path and held cgroup verification failed",
                    [missing, removal],
                ) from None
            partial = getattr(missing, "slurm_kernel_capture", None)
            if isinstance(partial, KernelCapture):
                observed = replace(
                    observed,
                    capture=KernelCapture(
                        partial.reads + observed.capture.reads,
                        partial.controls + observed.capture.controls,
                        partial.failed_control_path,
                        observed.capture.pinned_controls,
                    ),
                )
            return observed


def _held(fd: int, expected: KernelControl) -> KernelControl:
    value = os.fstat(fd)
    if (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode) != (
        expected.device,
        expected.inode,
        expected.uid,
        expected.gid,
        expected.mode,
    ):
        raise OwnershipConflict("Original cgroup descriptor identity changed")
    return expected


def pin_user_tree(
    original: SlurmCgroupMembership, control: OperationControl
) -> PinnedUserTree:
    original = SlurmCgroupMembership.model_validate(original)
    if original.step_id == "batch":
        raise OwnershipConflict("Only an original dedicated step can be pinned")
    readings = KernelReadings(control)
    descriptors: list[int] = []
    retained: list[int] = []
    primary: BaseException | None = None
    try:
        try:
            observer = read_process_identity(readings, os.getpid(), original.uid)
            if (observer.node_id, observer.boot_id) != (
                original.writer.node_id,
                original.writer.boot_id,
            ):
                raise OwnershipConflict("Original cgroup host/boot differs")
            mount = parse_mount(
                readings.read(
                    Path(f"/proc/{observer.process_id}/mountinfo"), 1024 * 1024
                )
            )
            if (mount.mount_id, os.makedev(mount.major, mount.minor)) != (
                original.mount_id,
                original.device,
            ):
                raise OwnershipConflict("Original cgroup mount differs")
            user = Path(original.user_path)
            controls = inspect_cgroup_chain(readings, user, mount)
            directory = controls[user]
            events = readings.inspect(user / "cgroup.events", directory=False)
            if (
                directory.inode != original.user_inode
                or events.device != directory.device
            ):
                raise OwnershipConflict("Original cgroup inode differs")
            fd = _open_path(user, descriptors, control, directory=True)
            _held(fd, directory)
            retained.append(os.dup(fd))
            event_fd = os.open(
                "cgroup.events", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
            )
            retained.append(event_fd)
            _held(event_fd, events)
            if tuple(os.readlink(f"/proc/self/fd/{f}") for f in retained) != (
                str(user),
                str(user / "cgroup.events"),
            ):
                raise OwnershipConflict(
                    "Original cgroup was removed or renamed before pin"
                )
            control.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all(tuple(reversed(descriptors)), primary)
    except BaseException as error:
        setattr(error, "slurm_kernel_capture", readings.capture())
        close_all(tuple(reversed(retained)), error)
        raise
    return PinnedUserTree(
        original,
        (retained[0], retained[1]),
        replace(
            readings.capture(),
            pinned_controls=(
                KernelPinnedControl(
                    "pinned",
                    directory,
                    events,
                    str(user),
                    str(user / "cgroup.events"),
                    None,
                ),
            ),
        ),
        directory,
        events,
    )
