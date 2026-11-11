"""Exact original ports: no fallback, rollback and original process lifetime."""

from pathlib import Path
import socket
import subprocess
import sys
import select
from typing import Any
import pytest
from lab_generate_skill.adapters.network import loopback_ports as ports
from test_loopback_ports import (
    namespace as namespace,
    deterministic as deterministic,
    Stop,
)
from test_slurm_commands import guard


def test_required_order_overlap_and_repeated_lease(deterministic: None) -> None:
    allocator = ports.LoopbackPorts(
        candidates=(20001, 20002, 20003), required_prefix=(20002, 20001)
    )
    lease = allocator.reserve(3, guard())
    assert lease.ports == (20002, 20001, 20003)
    with pytest.raises(ports.PortsUnavailable, match="no replacement"):
        allocator.reserve(3, guard())
    lease.release(guard())
    lease.release(guard())
    again = allocator.reserve(3, guard())
    assert again.ports == lease.ports
    again.release(guard())


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        [20001],
        (True,),
        (0,),
        (65536,),
        (20001, 20001),
        tuple(range(11000, 11033)),
    ],
)
def test_invalid_prefix_precedes_files(namespace: Path, bad: Any) -> None:
    with pytest.raises(ValueError):
        ports.LoopbackPorts(required_prefix=bad)
    assert not namespace.exists()


@pytest.mark.parametrize(
    "prefix,count,error",
    [
        ((20001, 20002), 1, ValueError),
        ((10080,), 1, ports.PortsUnavailable),
        ((40000,), 1, ports.PortsUnavailable),
    ],
)
def test_unsafe_or_oversized_prefix_precedes_files(
    namespace: Path,
    deterministic: None,
    prefix: tuple[int, ...],
    count: int,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        ports.LoopbackPorts(required_prefix=prefix).reserve(count, guard())
    assert not namespace.exists()


def test_partial_prefix_conflict_releases_only_own_locks(deterministic: None) -> None:
    original = ports.LoopbackPorts(required_prefix=(20002,)).reserve(1, guard())
    try:
        with pytest.raises(ports.PortsUnavailable, match="no replacement"):
            ports.LoopbackPorts(required_prefix=(20001, 20002)).reserve(2, guard())
        first = ports.LoopbackPorts(required_prefix=(20001,)).reserve(1, guard())
        first.release(guard())
        with pytest.raises(ports.PortsUnavailable):
            ports.LoopbackPorts(required_prefix=(20002,)).reserve(1, guard())
    finally:
        original.release(guard())


@pytest.mark.parametrize("at", [1, 2, 3, 4, 5])
def test_cancel_at_prefix_allocation_preserves_error_and_releases_partial(
    deterministic: None, at: int
) -> None:
    allocator = ports.LoopbackPorts(required_prefix=(20001, 20002))
    with pytest.raises(TimeoutError, match="original operation stopped"):
        allocator.reserve(2, Stop(at))
    lease = allocator.reserve(2, guard())
    assert lease.ports == (20001, 20002)
    lease.release(guard())


def test_actual_noncooperating_socket_does_not_choose_replacement(
    namespace: Path,
) -> None:
    original = ports.LoopbackPorts().reserve(1, guard())
    port = original.ports[0]
    original.release(guard())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
        with pytest.raises(ports.PortsUnavailable, match="no replacement"):
            ports.LoopbackPorts(required_prefix=(port,)).reserve(1, guard())
    candidate = ports.LoopbackPorts(required_prefix=(port,)).reserve(1, guard())
    assert candidate.ports == (port,)
    candidate.release(guard())


def test_fresh_process_refuses_held_origin_then_acquires_after_original_exit(
    namespace: Path,
) -> None:
    # Actual child process/lock lifetime. This is not proof of any site's full
    # resource closure, initial equivalence, source permission or Actor outcome.
    pick = ports.LoopbackPorts().reserve(1, guard())
    port = pick.ports[0]
    pick.release(guard())
    program = r"""
import sys
from pathlib import Path
from lab_generate_skill.adapters.network import port_files
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts, PortsUnavailable
class Control:
    def checkpoint(self): return 10.0
    def wait(self, seconds): raise AssertionError("no waiting")
port_files.namespace = lambda: Path(sys.argv[1])
try:
    lease = LoopbackPorts(required_prefix=(int(sys.argv[2]),)).reserve(1, Control())
except PortsUnavailable:
    print("busy", flush=True)
else:
    print("held", flush=True)
    if sys.argv[3] == "source":
        sys.stdin.readline()
    lease.release(Control())
"""
    command = (sys.executable, "-B", "-c", program, str(namespace), str(port))
    source = subprocess.Popen(
        (*command, "source"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert source.stdout is not None
        assert select.select([source.stdout], [], [], 10)[0]
        assert source.stdout.readline() == b"held\n"
        busy = subprocess.run(
            (*command, "candidate"), capture_output=True, check=True, timeout=10
        )
        assert busy.stdout == b"busy\n" and source.poll() is None
        _, err = source.communicate(b"close\n", timeout=10)
        assert source.returncode == 0 and err == b""
        candidate = subprocess.run(
            (*command, "candidate"), capture_output=True, check=True, timeout=10
        )
        assert candidate.stdout == b"held\n"
    finally:
        if source.poll() is None:
            source.kill()
        source.communicate(timeout=10)
