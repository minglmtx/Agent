"""Walk original exceptions/cleanup groups once, without altering their topology."""

from collections.abc import Iterator


def exception_chain(error: BaseException) -> Iterator[BaseException]:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(reversed(current.exceptions))
