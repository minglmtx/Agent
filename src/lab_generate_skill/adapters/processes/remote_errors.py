"""Bounded exception structure for worker diagnostics, never executable types.

Keep group order, explicit cause/context, cleanup children, errno and traceback locations. Do not
serialize arguments, locals, source lines or arbitrary messages containing data.
Truncation and cycles remain explicit; no remote diagnostic proves cleanup.
"""

from pydantic import Field
from lab_generate_skill.domain.validation import Contract

MAX_ERROR_NODES = 16
MAX_ERROR_DEPTH = 6
MAX_ERROR_FRAMES = 4


class RemoteFrame(Contract):
    filename: str = Field(min_length=1, max_length=192)
    function: str = Field(min_length=1, max_length=64)
    line: int = Field(ge=1)


class RemoteError(Contract):
    type_name: str = Field(min_length=1, max_length=128)
    reason_code: str | None = Field(default=None, max_length=128)
    errno: int | None = None
    frames: tuple[RemoteFrame, ...] = Field(default=(), max_length=MAX_ERROR_FRAMES)
    children: tuple["RemoteError", ...] = Field(default=(), max_length=MAX_ERROR_NODES)
    cause: "RemoteError | None" = None
    context: "RemoteError | None" = None
    context_suppressed: bool = False
    truncated: bool = False


def describe_error(error: BaseException) -> RemoteError:
    """Capture safe locations and bounded topology without str(error)/repr(data)."""
    remaining = MAX_ERROR_NODES
    active: set[int] = set()

    def visit(current: BaseException, depth: int) -> RemoteError:
        nonlocal remaining
        remaining -= 1
        limited = depth >= MAX_ERROR_DEPTH or id(current) in active
        frames: list[RemoteFrame] = []
        tb = current.__traceback__
        while tb is not None:
            frames.append(
                RemoteFrame(
                    filename=tb.tb_frame.f_code.co_filename[-192:] or "unknown",
                    function=tb.tb_frame.f_code.co_name[:64] or "unknown",
                    line=max(1, tb.tb_lineno),
                )
            )
            tb = tb.tb_next
        limited_frames = len(frames) > MAX_ERROR_FRAMES
        children: list[RemoteError] = []
        cause = context = None
        truncated = limited or limited_frames
        active.add(id(current))
        if not limited:
            if isinstance(current, BaseExceptionGroup):
                for child in current.exceptions:
                    if remaining == 0:
                        truncated = True
                        break
                    children.append(visit(child, depth + 1))
            if current.__cause__ is not None:
                if remaining:
                    cause = visit(current.__cause__, depth + 1)
                else:
                    truncated = True
            if not isinstance(current, BaseExceptionGroup):
                cleanup = getattr(current, "cleanup_errors", ())
                if isinstance(cleanup, tuple):
                    for child in cleanup:
                        if not isinstance(child, BaseException):
                            continue
                        if remaining == 0:
                            truncated = True
                            break
                        children.append(visit(child, depth + 1))
            if (
                current.__context__ is not None
                and current.__context__ is not current.__cause__
            ):
                if remaining:
                    context = visit(current.__context__, depth + 1)
                else:
                    truncated = True
        active.discard(id(current))
        reason = getattr(current, "reason_code", None)
        return RemoteError(
            type_name=type(current).__name__[:128] or "UnknownError",
            reason_code=reason[:128] if type(reason) is str else None,
            errno=current.errno if isinstance(current, OSError) else None,
            frames=tuple(frames[-MAX_ERROR_FRAMES:]),
            children=tuple(children),
            cause=cause,
            context=context,
            context_suppressed=current.__suppress_context__,
            truncated=truncated,
        )

    return visit(error, 0)


def validate_error_budget(error: RemoteError) -> None:
    count = 0

    def visit(current: RemoteError, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_ERROR_NODES or depth > MAX_ERROR_DEPTH:
            raise ValueError("Worker diagnostic exceeds structural budget")
        for child in (*current.children, current.cause, current.context):
            if child is not None:
                visit(child, depth + 1)

    visit(error, 0)
