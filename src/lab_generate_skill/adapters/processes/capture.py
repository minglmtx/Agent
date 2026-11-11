"""Command diagnostics and direct-child cleanup facts, not writer quiescence.

A reaped leader does not prove escaped descendants or site resources stopped.
No field authorizes replaying an external operation after an error.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.process_identity import (
    ProcessTermination as ProcessTermination,
)


@dataclass(frozen=True)
class CommandCapture:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: bytes
    stderr: bytes
    complete: bool
    # Absent facts from a scripted/test capture remain unverified, never clean.
    termination: ProcessTermination | None = None


class CommandFailure(RuntimeError):
    def __init__(self, reason: str, capture: CommandCapture) -> None:
        self.reason_code, self.capture = reason, capture
        super().__init__(f"Supervised command failed: {reason}")


def retained_capture(error: BaseException) -> CommandCapture | None:
    """Find the original command, including an interrupted supervisor's capture."""
    if isinstance(error, CommandFailure):
        return error.capture
    capture = getattr(error, "command_capture", None)
    if isinstance(capture, CommandCapture):
        return capture
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            found = retained_capture(child)
            if found is not None:
                return found
    return None


def require_reaped(capture: CommandCapture) -> ProcessTermination:
    """Fail closed for missing or incomplete controlled-worker cleanup facts.

    The caller must separately establish that its trusted worker cannot create
    unmanaged writers/descendants. This checks direct-child cleanup only.
    """
    termination = capture.termination
    if (
        termination is None
        or termination.state != "reaped"
        or termination.cleanup_errors
    ):
        raise CommandFailure("PROCESS_CLEANUP_UNCONFIRMED", capture)
    return termination
