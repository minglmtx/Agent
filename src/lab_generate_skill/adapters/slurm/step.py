"""Readonly controller queries; caller persists/combines raw facts.

Does not submit, cancel, signal, retry failed queries or grant rights.
Original accounting and kernel/installed-worker evidence remain separate gates.
"""

from dataclasses import dataclass
from pathlib import Path

from lab_generate_skill.adapters.processes.capture import (
    require_reaped,
    retained_capture,
)
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.ports.lifecycle import OperationControl
from .commands import CommandCapture, CommandFailure, SlurmCommandRunner
from .step_codec import parse_step_json, check_step_absent
from .step_text import check_step_text


@dataclass(frozen=True)
class SlurmStepObservation:
    target: SlurmStepTarget
    controller: SlurmControllerStep | None
    commands: tuple[CommandCapture, ...]


class SlurmStepObserver:
    def __init__(self, runner: SlurmCommandRunner, *, scontrol: Path) -> None:
        if (
            not isinstance(scontrol, Path)
            or not scontrol.is_absolute()
            or ".." in scontrol.parts
        ):
            raise ValueError("Step query executable must be an explicit absolute path")
        self._runner, self._scontrol = runner, str(scontrol)

    def observe(
        self,
        target: SlurmStepTarget,
        control: OperationControl,
        *,
        require_absent: bool = False,
    ) -> SlurmStepObservation:
        target = SlurmStepTarget.model_validate(target)
        if type(require_absent) is not bool:
            raise ValueError("Step observation mode must be an explicit boolean")
        commands: list[CommandCapture] = []
        stage = "initial_guard"
        try:
            control.checkpoint()
            parsed: SlurmControllerStep | None = None
            for stage in (
                ("absent",) if require_absent else ("before", "uid", "after")
            ):
                argv = (
                    self._scontrol,
                    "show",
                    "step",
                    target.step_key,
                    "-o" if stage == "uid" else "--json",
                )
                control.checkpoint()
                capture = self._runner.run(argv, control)
                commands.append(capture)
                ending = require_reaped(capture)
                if (
                    capture.argv != argv
                    or capture.complete is not True
                    or type(capture.returncode) is not int
                    or capture.returncode != 0
                    or ending.returncode != 0
                    or ending.kill_requested
                    or capture.stderr
                ):
                    raise CommandFailure("INVALID_STEP_QUERY_RESULT", capture)
                control.checkpoint()
                if stage == "absent":
                    try:
                        check_step_absent(capture.stdout, target)
                    except ValueError as error:
                        # Runner/control ValueError must never become a state poll.
                        setattr(error, "slurm_absence_response", True)
                        raise
                elif stage == "uid":
                    assert parsed is not None
                    check_step_text(capture.stdout, parsed)
                else:
                    current = parse_step_json(capture.stdout, target)
                    if parsed is not None and current != parsed:
                        raise ValueError(
                            "Step controller identity changed during observation"
                        )
                    parsed = current
            control.checkpoint()
            return SlurmStepObservation(target, parsed, tuple(commands))
        except BaseException as error:
            failed = retained_capture(error)
            if failed is not None and not any(c is failed for c in commands):
                commands.append(failed)
            setattr(error, "slurm_step_commands", tuple(commands))
            setattr(error, "slurm_step_stage", stage)
            raise

    def wait_absent(
        self, expected: SlurmControllerStep, control: OperationControl
    ) -> SlurmStepObservation:
        """Bounded observation of a known RUNNING-to-absent controller transition.

        No retry of failed queries or unknown responses. Keep every raw query.
        Kernel closure remains independently mandatory, never inferred here.
        """
        expected = SlurmControllerStep.model_validate(expected)
        commands: list[CommandCapture] = []
        try:
            for index in range(10):
                try:
                    observed = self.observe(
                        expected.target, control, require_absent=True
                    )
                except ValueError as error:
                    partial: tuple[CommandCapture, ...] = getattr(
                        error, "slurm_step_commands", ()
                    )
                    if (
                        getattr(error, "slurm_absence_response", False) is not True
                        or getattr(error, "slurm_step_stage", None) != "absent"
                        or len(partial) != 1
                    ):
                        raise
                    commands.extend(partial)
                    current = parse_step_json(partial[0].stdout, expected.target)
                    if current != expected:
                        raise ValueError(
                            "Original controller identity changed while closing"
                        ) from error
                    if index == 9:
                        raise TimeoutError(
                            "Original controller absence remains unconfirmed"
                        ) from error
                    # Spread the fixed ten observations over the existing guard.
                    # Abrupt Slurm task cleanup can outlive a one-second burst.
                    # No extension of the deadline or retry of a failed query.
                    control.wait(min(1.0, control.checkpoint() / (10 - index)))
                else:
                    commands.extend(observed.commands)
                    return SlurmStepObservation(expected.target, None, tuple(commands))
        except BaseException as error:
            for capture in getattr(error, "slurm_step_commands", ()):
                if not any(c is capture for c in commands):
                    commands.append(capture)
            setattr(error, "slurm_step_commands", tuple(commands))
            raise
        raise AssertionError("Bounded absence observation exhausted without outcome")
