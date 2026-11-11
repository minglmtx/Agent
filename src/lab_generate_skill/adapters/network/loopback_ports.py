"""Held flock leases for IPv4 loopback services, independent of site semantics.

No port is selected in the kernel ephemeral range (or browser-blocked 10080).
Probe sockets close before handoff, while stable lock fds remain held. A process
ignoring this namespace can still win bind: service startup must fail rather
than silently choosing a new port. This adapter grants no execution authority.
"""

import errno
import fcntl
import os
from pathlib import Path
import random
import socket
import threading
from lab_generate_skill.ports.lifecycle import OperationControl
from . import port_files


class PortsUnavailable(RuntimeError):
    """The single bounded scan found fewer ports than requested."""


def ephemeral_range() -> tuple[int, int]:
    fields = Path("/proc/sys/net/ipv4/ip_local_port_range").read_text().split()
    if len(fields) != 2:
        raise ValueError("Malformed kernel ephemeral port range")
    lower, upper = map(int, fields)
    if not 1 <= lower <= upper <= 65535:
        raise ValueError("Invalid kernel ephemeral port range")
    return lower, upper


def probe(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    primary: BaseException | None = None
    try:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                return False
            raise
        return True
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            sock.close()
        except BaseException as error:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Port probe and socket close failed", [primary, error]
                ) from None
            raise


class HeldLoopbackPorts:
    def __init__(self, ports: tuple[int, ...], descriptors: list[int]) -> None:
        self._ports = ports
        self._descriptors = descriptors
        self._owner = (os.getpid(), threading.get_ident())
        self._released = False
        self._error: BaseException | None = None

    @property
    def ports(self) -> tuple[int, ...]:
        return self._ports

    def release(self, control: OperationControl) -> None:
        if self._owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("Port lease cannot leave its original process/thread")
        if self._error is not None:
            raise RuntimeError(
                "Original port release failed; do not retry uncertain fds"
            ) from self._error
        if self._released:
            return
        control.checkpoint()
        errors = port_files.close_descriptors(self._descriptors)
        if errors:
            self._error = BaseExceptionGroup("Port lease close failed", errors)
            raise self._error
        self._released = True
        control.checkpoint()


class LoopbackPorts:
    def __init__(
        self,
        *,
        candidates: tuple[int, ...] | None = None,
        required_prefix: tuple[int, ...] = (),
    ) -> None:
        values = tuple(range(10000, 30000)) if candidates is None else candidates
        if (
            type(values) is not tuple
            or not values
            or len(values) > 64512
            or any(
                type(port) is not int or not 1024 <= port <= 65535 for port in values
            )
            or len(set(values)) != len(values)
        ):
            raise ValueError("Expected distinct immutable unprivileged port candidates")
        self._candidates = values
        if (
            type(required_prefix) is not tuple
            or len(required_prefix) > 32
            or any(
                type(p) is not int or not 1024 <= p <= 65535 for p in required_prefix
            )
            or len(set(required_prefix)) != len(required_prefix)
        ):
            raise ValueError("Distinct immutable unprivileged required ports expected")
        self._required = required_prefix

    def reserve(self, count: int, control: OperationControl) -> HeldLoopbackPorts:
        if type(count) is not int or not 1 <= count <= 32:
            raise ValueError("Port count must be an integer from 1 through 32")
        if len(self._required) > count:
            raise ValueError("Required prefix exceeds requested port count")
        control.checkpoint()
        lower, upper = ephemeral_range()
        if any(p == 10080 or lower <= p <= upper for p in self._required):
            raise PortsUnavailable("Required original port is not a safe service port")
        candidates = [
            p
            for p in self._candidates
            if p != 10080 and not lower <= p <= upper and p not in self._required
        ]
        if len(candidates) + len(self._required) < count:
            raise PortsUnavailable("Insufficient non-ephemeral candidates")
        random.SystemRandom().shuffle(candidates)
        candidates = [*self._required, *candidates]
        control.checkpoint()
        descriptors: list[int] = []
        selected: list[int] = []
        directory: list[int] = []
        try:
            directory.append(port_files.open_namespace())
            for port in candidates:
                control.checkpoint()
                fd = os.open(
                    str(port),
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_NOFOLLOW
                    | os.O_NONBLOCK
                    | os.O_CLOEXEC,
                    0o600,
                    dir_fd=directory[0],
                )
                descriptors.append(fd)  # retain before validation/probe/checkpoint
                port_files.validate_file(fd)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno not in (errno.EAGAIN, errno.EACCES):
                        raise
                    busy = True
                else:
                    busy = not probe(port)
                if busy:
                    # Pop before close: never retry an ambiguous close by fd number.
                    os.close(descriptors.pop())
                    if port in self._required:
                        raise PortsUnavailable(
                            "Original required port is busy; no replacement"
                        )
                    continue
                selected.append(port)
                control.checkpoint()
                if len(selected) == count:
                    errors = port_files.close_descriptors(directory)
                    if errors:
                        raise BaseExceptionGroup("Port namespace close failed", errors)
                    control.checkpoint()
                    return HeldLoopbackPorts(tuple(selected), descriptors)
            raise PortsUnavailable("Requested ports unavailable in this bounded scan")
        except BaseException as primary:
            errors = port_files.close_descriptors(
                descriptors
            ) + port_files.close_descriptors(directory)
            if errors:
                raise BaseExceptionGroup(
                    "Port allocation and cleanup failed", [primary, *errors]
                ) from None
            raise
