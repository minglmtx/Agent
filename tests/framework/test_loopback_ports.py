"""Port lifetime, contention and failure effects without starting site services."""

import errno
import fcntl
import os
from pathlib import Path
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import pytest
from lab_generate_skill.adapters.network import loopback_ports as ports
from lab_generate_skill.adapters.network import port_files
from lab_generate_skill.sites.shopping_admin.service_ports import admin_ports
from test_slurm_commands import guard


@pytest.fixture
def namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "locks"
    monkeypatch.setattr(port_files, "namespace", lambda: root)
    return root


@pytest.fixture
def deterministic(namespace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ports, "ephemeral_range", lambda: (32768, 60999))
    monkeypatch.setattr(ports, "probe", lambda port: True)


def test_real_reserve_map_hold_release_and_reacquire(namespace: Path) -> None:
    lease = ports.LoopbackPorts().reserve(5, guard())
    try:
        addresses = admin_ports(lease)
        assert (
            addresses.web,
            addresses.database,
            addresses.redis,
            addresses.search,
            addresses.transport,
        ) == lease.ports
        assert len(set(lease.ports)) == 5
        lower, upper = ports.ephemeral_range()
        assert all(not lower <= p <= upper and p != 10080 for p in lease.ports)
        inodes = [(namespace / str(p)).stat().st_ino for p in lease.ports]
        assert all(not os.get_inheritable(fd) for fd in lease._descriptors)
        with pytest.raises(ports.PortsUnavailable):
            ports.LoopbackPorts(candidates=lease.ports).reserve(1, guard())
    finally:
        lease.release(guard())
    lease.release(guard())
    assert [(namespace / str(p)).stat().st_ino for p in lease.ports] == inodes
    second = ports.LoopbackPorts(candidates=lease.ports).reserve(5, guard())
    second.release(guard())


@pytest.mark.parametrize("count", [None, True, 0, -1, 33, "5", 1.0])
def test_bad_count_has_no_filesystem_effect(namespace: Path, count: Any) -> None:
    with pytest.raises(ValueError):
        ports.LoopbackPorts().reserve(count, guard())
    assert not namespace.exists()


@pytest.mark.parametrize(
    "values", [(), [], (10001, 10001), (True,), (1023,), (65536,), ("12000",)]
)
def test_bad_candidates_have_no_filesystem_effect(namespace: Path, values: Any) -> None:
    with pytest.raises(ValueError):
        ports.LoopbackPorts(candidates=values)
    assert not namespace.exists()


def test_filter_kernel_range_browser_port_and_count_boundary(
    deterministic: None,
) -> None:
    lease = ports.LoopbackPorts(candidates=(1024, 10080, 32768, 60999, 65535)).reserve(
        2, guard()
    )
    assert set(lease.ports) == {1024, 65535}
    lease.release(guard())
    lease = ports.LoopbackPorts(candidates=tuple(range(11000, 11032))).reserve(
        32, guard()
    )
    assert len(lease.ports) == 32
    lease.release(guard())


def test_insufficient_filtered_candidates_does_not_create_root(
    namespace: Path, deterministic: None
) -> None:
    with pytest.raises(ports.PortsUnavailable):
        ports.LoopbackPorts(candidates=(10080, 32768, 60999)).reserve(1, guard())
    assert not namespace.exists()


@pytest.mark.parametrize(
    "text", ["", "20", "a b", "0 100", "60000 30000", "1024 65536"]
)
def test_invalid_kernel_range_rejects_before_effects(
    namespace: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: text)
    with pytest.raises(ValueError):
        ports.LoopbackPorts().reserve(1, guard())
    assert not namespace.exists()


@pytest.mark.parametrize("kind", ["directory", "symlink", "hardlink", "fifo", "public"])
def test_unsafe_lock_objects_are_retained_and_refused(
    namespace: Path, deterministic: None, kind: str
) -> None:
    namespace.mkdir(mode=0o700)
    target = namespace / "20001"
    if kind == "directory":
        target.mkdir()
    elif kind == "symlink":
        target.symlink_to(namespace / "missing")
    elif kind == "fifo":
        os.mkfifo(target, 0o600)
    else:
        target.write_bytes(b"keep")
        target.chmod(0o600 if kind == "hardlink" else 0o666)
        if kind == "hardlink":
            os.link(target, namespace / "other")
    original = target.lstat()
    with pytest.raises((OSError, ValueError)):
        ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    assert target.lstat() == original


@pytest.mark.parametrize("kind", ["public", "symlink"])
def test_unsafe_namespace_refused(namespace: Path, kind: str) -> None:
    if kind == "public":
        namespace.mkdir(mode=0o755)
        namespace.chmod(0o755)
    else:
        other = namespace.parent / "other"
        other.mkdir(mode=0o700)
        namespace.symlink_to(other, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        ports.LoopbackPorts().reserve(1, guard())
    assert not list(namespace.iterdir())


def test_bound_noncooperating_socket_is_skipped(namespace: Path) -> None:
    lease = ports.LoopbackPorts().reserve(1, guard())
    port = lease.ports[0]
    lease.release(guard())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
        with pytest.raises(ports.PortsUnavailable):
            ports.LoopbackPorts(candidates=(port,)).reserve(1, guard())
    lease = ports.LoopbackPorts(candidates=(port,)).reserve(1, guard())
    lease.release(guard())


def test_partial_allocation_exhaustion_releases_owned_locks(
    deterministic: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ports, "probe", lambda port: port == 20001)
    allocator = ports.LoopbackPorts(candidates=(20001, 20002))
    with pytest.raises(ports.PortsUnavailable):
        allocator.reserve(2, guard())
    lease = allocator.reserve(1, guard())
    assert lease.ports == (20001,)
    lease.release(guard())


class Stop:
    def __init__(self, calls: int) -> None:
        self.calls = calls

    def checkpoint(self) -> float:
        self.calls -= 1
        if self.calls == 0:
            raise TimeoutError("original operation stopped")
        return 10.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


@pytest.mark.parametrize("at", [1, 2, 3, 4, 5])
def test_cancel_at_each_acquisition_boundary_releases_partial_locks(
    deterministic: None, at: int
) -> None:
    allocator = ports.LoopbackPorts(candidates=(20001,))
    with pytest.raises(TimeoutError):
        allocator.reserve(1, Stop(at))
    lease = allocator.reserve(1, guard())
    lease.release(guard())


def test_release_cancel_preserves_locks_then_independent_cleanup(
    deterministic: None,
) -> None:
    lease = ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    with pytest.raises(TimeoutError):
        lease.release(Stop(1))
    with pytest.raises(ports.PortsUnavailable):
        ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    with pytest.raises(TimeoutError):
        lease.release(Stop(2))  # close succeeded, final checkpoint stopped
    lease.release(guard())
    new = ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    new.release(guard())


def test_cross_thread_cannot_release_original_handle(deterministic: None) -> None:
    lease = ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lease.release, guard())
            with pytest.raises(RuntimeError, match="original process/thread"):
                future.result(timeout=5)
        with pytest.raises(ports.PortsUnavailable):
            ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    finally:
        lease.release(guard())


def test_independent_process_observes_lock_then_release(namespace: Path) -> None:
    lease = ports.LoopbackPorts().reserve(1, guard())
    program = r"""
import sys
from pathlib import Path
from lab_generate_skill.adapters.network import port_files
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts, PortsUnavailable
class Control:
    def checkpoint(self): return 5.0
    def wait(self, seconds): raise AssertionError("no waits expected")
port_files.namespace = lambda: Path(sys.argv[1])
try:
    lease = LoopbackPorts(candidates=(int(sys.argv[2]),)).reserve(1, Control())
except PortsUnavailable:
    print("busy")
else:
    lease.release(Control())
    print("acquired")
"""
    command = (sys.executable, "-B", "-c", program, str(namespace), str(lease.ports[0]))
    try:
        result = subprocess.run(command, capture_output=True, timeout=10, check=True)
        assert result.stdout == b"busy\n"
    finally:
        lease.release(guard())
    result = subprocess.run(command, capture_output=True, timeout=10, check=True)
    assert result.stdout == b"acquired\n"


def test_probe_failure_plus_close_failure_retains_both_and_releases_other_fds(
    deterministic: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_close = os.close
    primary = OSError(errno.EIO, "probe storage failure")
    cleanup = OSError(errno.EIO, "close uncertain")

    def bad_probe(port: int) -> bool:
        raise primary

    def bad_close(fd: int) -> None:
        is_lock = os.readlink(f"/proc/self/fd/{fd}").endswith("/20001")
        real_close(fd)
        if is_lock:
            raise cleanup

    with monkeypatch.context() as patch:
        patch.setattr(ports, "probe", bad_probe)
        patch.setattr(os, "close", bad_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
        assert caught.value.exceptions == (primary, cleanup)
    lease = ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    lease.release(guard())


def test_release_close_error_attempts_all_and_never_retries_numeric_fds(
    deterministic: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    lease = ports.LoopbackPorts(candidates=(20001, 20002)).reserve(2, guard())
    real_close = os.close
    calls: list[int] = []

    def bad_close(fd: int) -> None:
        calls.append(fd)
        real_close(fd)
        raise OSError(errno.EIO, "injected uncertain close")

    with monkeypatch.context() as patch:
        patch.setattr(os, "close", bad_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            lease.release(guard())
        assert len(caught.value.exceptions) == 2 and len(calls) == 2
        with pytest.raises(RuntimeError, match="do not retry") as repeated:
            lease.release(guard())
        assert repeated.value.__cause__ is caught.value
        assert len(calls) == 2
    new = ports.LoopbackPorts(candidates=(20001, 20002)).reserve(2, guard())
    new.release(guard())


def test_flock_infrastructure_error_is_not_treated_as_contention(
    deterministic: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = OSError(errno.EIO, "broken lock infrastructure")
    with monkeypatch.context() as patch:

        def fail(fd: int, operation: int) -> None:
            raise failure

        patch.setattr(fcntl, "flock", fail)
        with pytest.raises(OSError) as caught:
            ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
        assert caught.value is failure
    lease = ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    lease.release(guard())


@pytest.mark.parametrize(
    "values", [(1, 2), [12001] * 5, (12001,) * 5, (True, 12002, 12003, 12004, 12005)]
)
def test_admin_mapping_refuses_invalid_lease_values(values: Any) -> None:
    class Lease:
        ports = values

        def release(self, control: Any) -> None:
            raise AssertionError("Mapping must not release its caller's lease")

    with pytest.raises(ValueError):
        admin_ports(Lease())


def test_canonical_namespace_uses_existing_cooperative_lock_protocol() -> None:
    root = Path("/tmp") / f"lab-admin-ports-{os.getuid()}"
    assert port_files.namespace() == root
    lease = ports.LoopbackPorts().reserve(1, guard())
    port = lease.ports[0]
    try:
        with (root / str(port)).open("a+") as existing_caller:
            with pytest.raises(BlockingIOError):
                fcntl.flock(existing_caller.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        lease.release(guard())
    with (root / str(port)).open("a+") as existing_caller:
        fcntl.flock(existing_caller.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ports.PortsUnavailable):
            ports.LoopbackPorts(candidates=(port,)).reserve(1, guard())
    again = ports.LoopbackPorts(candidates=(port,)).reserve(1, guard())
    again.release(guard())


@pytest.mark.parametrize("mode", [0o600, 0o640, 0o604, 0o644])
def test_readonly_mode_bits_preserve_existing_inode(
    namespace: Path, deterministic: None, mode: int
) -> None:
    namespace.mkdir(mode=0o700)
    original = namespace / "20001"
    original.write_bytes(b"legacy lock contents retained")
    original.chmod(mode)
    before = original.stat()
    lease = ports.LoopbackPorts(candidates=(20001,)).reserve(1, guard())
    lease.release(guard())
    assert original.stat() == before
    assert original.read_bytes() == b"legacy lock contents retained"


def test_probe_permission_and_socket_close_errors_remain_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = PermissionError(errno.EACCES, "bind denied")
    second = OSError(errno.EIO, "socket close uncertain")

    class Socket:
        def bind(self, address: tuple[str, int]) -> None:
            raise first

        def close(self) -> None:
            raise second

    monkeypatch.setattr(socket, "socket", lambda *args: Socket())
    with pytest.raises(BaseExceptionGroup) as caught:
        ports.probe(20001)
    assert caught.value.exceptions == (first, second)
