"""Thin checked-result adapter over the existing bounded process transport."""

from lab_generate_skill.ports.lifecycle import OperationControl
from .commands import ProcessRunner
from .capture import CommandFailure, require_reaped


class CheckedNativeCommands:
    def __init__(self, runner: ProcessRunner) -> None:
        self.runner = runner

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        capture = self.runner.run(argv, control)
        require_reaped(capture)
        if not capture.complete or capture.returncode != 0:
            raise CommandFailure("NATIVE_COMMAND_FAILED", capture)
        try:
            control.checkpoint()
        except Exception as error:
            setattr(error, "command_capture", capture)
            raise
        return capture.stdout
