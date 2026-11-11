"""Read-only Slurm command adapter using the shared supervised process transport.

The public query interface keeps its 8 MiB output bound and accepts no stdin.
Process lifecycle/pipe handling lives in adapters.processes.commands.
"""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.commands import (
    CommandCapture as CommandCapture,
    CommandFailure as CommandFailure,
    ProcessRunner,
)


class SlurmCommandRunner:
    def __init__(
        self, *, max_output_bytes: int = 1024 * 1024, reap_timeout: float = 2.0
    ) -> None:
        if (
            type(max_output_bytes) is not int
            or not 1 <= max_output_bytes <= 8 * 1024 * 1024
        ):
            raise ValueError("Output bound must be an integer between 1 and 8 MiB")
        self._runner = ProcessRunner(
            max_output_bytes=max_output_bytes, reap_timeout=reap_timeout
        )

    def run(self, argv: tuple[str, ...], control: OperationControl) -> CommandCapture:
        return self._runner.run(argv, control)
