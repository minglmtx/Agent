"""Fixed argv and controller orchestration, including captured failures and stops."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.slurm.step_launch import (
    fixed_generator_step_argv,
    generator_step_name,
)
from lab_generate_skill.adapters.slurm.commands import (
    SlurmCommandRunner,
    CommandCapture,
    CommandFailure,
)
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl
from cgroup_fixtures import Control
from slurm_step_fixtures import FIXTURES, target, token, recorded, encoded, epoch_text


class Runner(SlurmCommandRunner):
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.change: dict[str, Any] = {}
        self.fail: BaseException | None = None
        self.drift = False
        self.absent = False

    def run(self, argv: tuple[str, ...], control: OperationControl) -> CommandCapture:
        self.calls.append(argv)
        raw = (
            FIXTURES
            / (
                "absent.json"
                if self.absent
                else "running.txt" if argv[-1] == "-o" else "running.json"
            )
        ).read_bytes()
        if not self.absent and argv[-1] == "-o":
            raw = epoch_text()
        if self.drift and len(self.calls) == 3:
            data = recorded()
            data["steps"][0]["time"]["start"]["number"] += 1
            raw = encoded(data)
        capture = replace(
            CommandCapture(
                argv, 0, raw, b"", True, ProcessTermination(123, "reaped", 0, False)
            ),
            **self.change,
        )
        if self.fail is not None:
            setattr(self.fail, "command_capture", capture)
            raise self.fail
        return capture


def observer(runner: Runner) -> SlurmStepObserver:
    return SlurmStepObserver(runner, scontrol=Path("/usr/bin/scontrol"))


def test_live_and_absent_repeat() -> None:
    runner = Runner()
    o = observer(runner)
    first = o.observe(target(), Control())
    second = o.observe(target(), Control())
    assert first == second and first.controller is not None and len(first.commands) == 3
    assert [x[-1] for x in runner.calls] == ["--json", "-o", "--json"] * 2
    assert all(x[3] == target().step_key for x in runner.calls)
    runner.absent = True
    absent = o.observe(target(), Control(), require_absent=True)
    assert absent.controller is None and len(absent.commands) == 1
    # Absence carries commands only, no tree-clean or recovery permission field.
    assert absent.target == target()


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"returncode": 1},
        {"returncode": True},
        {"argv": ("/wrong",)},
        {"stderr": b"warning"},
        {"termination": None},
        {"termination": ProcessTermination(123, "unconfirmed", None, True)},
        {"termination": ProcessTermination(123, "reaped", 0, True)},
        {"termination": ProcessTermination(123, "reaped", 1, False)},
        {"termination": ProcessTermination(123, "reaped", 0, False, ("close failed",))},
    ],
)
def test_invalid_command_cannot_be_a_success(change: dict[str, Any]) -> None:
    runner = Runner()
    runner.change = change
    with pytest.raises(CommandFailure) as caught:
        observer(runner).observe(target(), Control())
    assert len(runner.calls) == 1
    assert len(getattr(caught.value, "slurm_step_commands")) == 1
    assert getattr(caught.value, "slurm_step_stage") == "before"


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("deadline"),
        OSError("read"),
        BaseExceptionGroup(
            "primary and cleanup", [TimeoutError("deadline"), OSError("close")]
        ),
    ],
)
def test_original_command_failure_is_preserved(failure: BaseException) -> None:
    runner = Runner()
    runner.fail = failure
    with pytest.raises(BaseException) as caught:
        observer(runner).observe(target(), Control())
    assert caught.value is failure and len(runner.calls) == 1
    assert len(getattr(failure, "slurm_step_commands")) == 1


def test_controller_changes_between_queries() -> None:
    runner = Runner()
    runner.drift = True
    with pytest.raises(ValueError, match="changed during") as caught:
        observer(runner).observe(target(), Control())
    assert len(getattr(caught.value, "slurm_step_commands")) == 3


@pytest.mark.parametrize("stop_at", range(1, 9))
def test_stop_never_repeats_queries(stop_at: int) -> None:
    failure = TimeoutError("stop")

    class Stop(Control):
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if self.calls == stop_at:
                raise failure
            return 100.0

    runner = Runner()
    with pytest.raises(TimeoutError) as caught:
        observer(runner).observe(target(), Stop())
    assert caught.value is failure and len(runner.calls) <= 3
    assert len(getattr(failure, "slurm_step_commands")) == len(runner.calls)


@pytest.mark.parametrize(
    "path", [Path("relative"), Path("/bin/../scontrol"), "scontrol", None]
)
def test_invalid_query_binary(path: Any) -> None:
    with pytest.raises(ValueError):
        SlurmStepObserver(Runner(), scontrol=path)


def test_fixed_generator_argv_and_name() -> None:
    t = target()
    allocation = token()
    argv = fixed_generator_step_argv(
        allocation,
        t.execution,
        t.launcher.node_id,
        python_executable="/workspace/python",
        srun_executable="/usr/bin/srun",
    )
    assert argv[-5:] == (
        "/workspace/python",
        "-I",
        "-B",
        "-m",
        "lab_generate_skill.bootstrap.generator_worker",
    )
    assert "--jobid=4752096" in argv and "--nodelist=a0535" in argv
    assert "--job-name=" + generator_step_name(allocation) in argv
    assert "--gres=gpu:1" in argv and "--exact" in argv and "--exclusive" in argv
    assert "--unbuffered" in argv  # Otherwise srun holds the trailing partial line.
    assert argv == fixed_generator_step_argv(
        allocation,
        t.execution,
        t.launcher.node_id,
        python_executable="/workspace/python",
        srun_executable="/usr/bin/srun",
    )
    assert generator_step_name(allocation) != generator_step_name(
        allocation.model_copy(update={"allocation_id": "other"})
    )
    assert generator_step_name(allocation) != generator_step_name(
        allocation.model_copy(
            update={"owner": allocation.owner.model_copy(update={"run_id": "other"})}
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "relative",
        "/path/../python",
        "/path//python",
        "/python\x00",
        "/python\n",
        "/python\\x",
        True,
        None,
        "/" + "x" * 4096,
    ],
)
@pytest.mark.parametrize("which", ["python_executable", "srun_executable"])
def test_invalid_executable_before_effects(path: Any, which: str) -> None:
    kwargs = {
        "python_executable": "/workspace/python",
        "srun_executable": "/usr/bin/srun",
    }
    kwargs[which] = path
    with pytest.raises(ValueError):
        fixed_generator_step_argv(token(), target().execution, "a0535", **kwargs)


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "attempt", "attempt_id": "attempt"},
        {"resource_kind": "browser"},
        {"provider_id": "other"},
        {"owner": token().owner.model_copy(update={"job_id": "other"})},
    ],
)
def test_launch_requires_original_batch_generator(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        fixed_generator_step_argv(
            token().model_copy(update=changes),
            target().execution,
            "a0535",
            python_executable="/workspace/python",
            srun_executable="/usr/bin/srun",
        )
