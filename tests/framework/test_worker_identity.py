"""Process identity parsing plus actual Linux self observation on compute node."""

import os
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.processes.worker_identity import (
    parse_process_start,
    current_evidence_worker,
)


def stat(comm: bytes = b"worker", ticks: bytes = b"42") -> bytes:
    return b"123 (" + comm + b") S " + b" ".join([b"0"] * 18 + [ticks, b"999"])


@pytest.mark.parametrize(
    "comm", [b"worker", b"worker name", b"a) b (c)", b"line\nname)"]
)
def test_comm_delimiters_do_not_shift_start_time(comm: bytes) -> None:
    assert parse_process_start(stat(comm), 123) == 42


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"x" * 16385,
        b"123 S 0",
        b"124 (worker) S 0",
        b"123 (worker) S 0",
        stat(ticks=b"0"),
        stat(ticks=b"-1"),
        stat(ticks=b"1.2"),
    ],
)
def test_bad_or_truncated_stat_rejected(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_process_start(raw, 123)


@pytest.mark.parametrize("pid", [True, 0, -1, "123", None])
def test_bad_pid_type_or_value_rejected(pid: object) -> None:
    with pytest.raises(ValueError):
        parse_process_start(stat(), cast(int, pid))


def test_actual_worker_is_same_incarnation_on_repeated_observation() -> None:
    first = current_evidence_worker()
    assert first == current_evidence_worker()
    assert first.process_id == os.getpid() and first.start_ticks > 0
    assert first.boot_id == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
