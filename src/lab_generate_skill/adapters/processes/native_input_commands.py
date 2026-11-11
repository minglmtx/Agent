"""Memory-only native selector input over the existing supervised transport."""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import MAX_NATIVE_INPUT_BYTES
from .commands import ProcessRunner
from .capture import CommandFailure, require_reaped


class CheckedNativeInputCommands:
    def __init__(self, runner: ProcessRunner) -> None:
        self.runner = runner

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        if type(data) is not bytes or not 0 < len(data) <= MAX_NATIVE_INPUT_BYTES:
            raise ValueError(
                "Native selector input must be nonempty bytes within 8 KiB"
            )
        capture = self.runner.run(argv, control, stdin_bytes=data)
        require_reaped(capture)
        if not capture.complete or capture.returncode != 0:
            raise CommandFailure("NATIVE_INPUT_COMMAND_FAILED", capture)
        try:
            control.checkpoint()
        except BaseException as error:
            setattr(error, "command_capture", capture)
            raise
        return capture.stdout
