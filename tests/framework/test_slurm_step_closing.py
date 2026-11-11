"""Only a known RUNNING-to-absent transition may be observed repeatedly."""

from dataclasses import replace
from collections.abc import Sequence
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.slurm.step_codec import parse_step_json
from lab_generate_skill.adapters.slurm.commands import (
    SlurmCommandRunner,
    CommandCapture,
)
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl
from cgroup_fixtures import Control
from slurm_step_fixtures import FIXTURES, target, recorded, encoded


class Clock(Control):
    def __init__(self) -> None:
        self.waits: list[float] = []
        self.stop: BaseException | None = None

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)
        if self.stop is not None:
            raise self.stop


class SequenceRunner(SlurmCommandRunner):
    def __init__(self, replies: Sequence[bytes | BaseException], **change: Any) -> None:
        self.replies, self.change = replies, change
        self.calls: list[CommandCapture] = []

    def run(self, argv: tuple[str, ...], control: OperationControl) -> CommandCapture:
        value = self.replies[len(self.calls)]
        capture = replace(
            CommandCapture(
                argv,
                0,
                value if isinstance(value, bytes) else RUNNING,
                b"",
                True,
                ProcessTermination(123, "reaped", 0, False),
            ),
            **self.change,
        )
        self.calls.append(capture)
        if isinstance(value, BaseException):
            setattr(value, "command_capture", capture)
            raise value
        return capture


RUNNING = (FIXTURES / "running.json").read_bytes()
ABSENT = (FIXTURES / "absent.json").read_bytes()


def close(runner: SequenceRunner, control: Clock) -> Any:
    return SlurmStepObserver(runner, scontrol=Path("/usr/bin/scontrol")).wait_absent(
        parse_step_json(RUNNING, target()), control
    )


@pytest.mark.parametrize("count", [0, 1, 9])
def test_known_transition_retains_every_observation(count: int) -> None:
    runner = SequenceRunner([RUNNING] * count + [ABSENT])
    control = Clock()
    observed = close(runner, control)
    assert observed.controller is None and observed.target == target()
    assert observed.commands == tuple(runner.calls)
    assert control.waits == [1.0] * count
    assert all(c.argv[3] == target().step_key for c in runner.calls)


def test_pending_is_bounded_and_never_reported_absent() -> None:
    runner = SequenceRunner([RUNNING] * 10)
    control = Clock()
    with pytest.raises(TimeoutError) as caught:
        close(runner, control)
    assert len(runner.calls) == 10 and len(control.waits) == 9
    assert getattr(caught.value, "slurm_step_commands") == tuple(runner.calls)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "malformed",
        "identity",
        "epoch",
        "state",
        "warning",
        "query",
        "query_value",
        "partial",
        "stderr",
    ],
)
def test_unknown_query_never_polled_again(kind: str) -> None:
    raw: bytes | BaseException = RUNNING
    change: dict[str, Any] = {}
    if kind == "empty":
        raw = b""
    elif kind == "malformed":
        raw = b"{broken"
    elif kind == "query":
        raw = OSError("query failed")
    elif kind == "query_value":
        raw = ValueError("query failed after capturing a valid response")
    elif kind == "partial":
        change["complete"] = False
    elif kind == "stderr":
        change["stderr"] = b"warning"
    else:
        data = recorded()
        if kind == "identity":
            data["steps"][0]["srun"]["pid"] += 1
        elif kind == "epoch":
            data["steps"][0]["time"]["start"]["number"] += 1
        elif kind == "state":
            data["steps"][0]["state"] = ["COMPLETED"]
        else:
            data["warnings"] = []
        raw = encoded(data)
    runner = SequenceRunner([raw], **change)
    control = Clock()
    with pytest.raises(Exception) as caught:
        close(runner, control)
    assert len(runner.calls) == 1 and not control.waits
    assert getattr(caught.value, "slurm_step_commands") == tuple(runner.calls)
    if isinstance(raw, BaseException):
        assert caught.value is raw


def test_stop_preserves_pending_query_and_no_further_observation() -> None:
    runner, control = SequenceRunner([RUNNING]), Clock()
    control.stop = TimeoutError("cleanup deadline")
    with pytest.raises(TimeoutError) as caught:
        close(runner, control)
    assert caught.value is control.stop and len(runner.calls) == 1
    assert getattr(caught.value, "slurm_step_commands") == tuple(runner.calls)


def test_observation_spacing_uses_remaining_guard_without_extension() -> None:
    class ShortClock(Clock):
        remaining = 0.25

        def checkpoint(self) -> float:
            if self.remaining <= 0:
                raise TimeoutError("original guard exhausted")
            return self.remaining

        def wait(self, seconds: float) -> None:
            assert 0 < seconds <= self.remaining
            self.waits.append(seconds)
            self.remaining -= seconds

    runner = SequenceRunner([RUNNING] * 9 + [ABSENT])
    control = ShortClock()
    observed = close(runner, control)
    assert observed.controller is None and len(runner.calls) == 10
    assert sum(control.waits) < 0.25 and len(control.waits) == 9
    assert control.waits == pytest.approx([0.025] * 9)
