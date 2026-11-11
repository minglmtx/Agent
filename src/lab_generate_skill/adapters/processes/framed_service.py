"""Shared bounded service loop; role codecs own their versioned wire contracts."""

from collections.abc import Callable
from typing import BinaryIO, Protocol, TypeVar
from lab_generate_skill.domain.validation import Contract
from .stream_frames import read_frame, write_frame

Command = TypeVar("Command", bound=Contract, contravariant=True)
Reply = TypeVar("Reply", bound=Contract, covariant=True)


class FramedService(Protocol[Command, Reply]):
    @property
    def closed(self) -> bool: ...
    def handle(self, command: Command) -> Reply: ...
    def close(self) -> None: ...


def serve_framed(
    service: FramedService[Command, Reply],
    source: BinaryIO,
    sink: BinaryIO,
    *,
    decode: Callable[[bytes], Command],
    limit: int,
    first: Command | None,
) -> None:
    primary: BaseException | None = None
    try:
        while not service.closed:
            if first is not None:
                command, first = first, None
            else:
                raw = read_frame(source, limit)
                if raw is None:
                    break
                command = decode(raw)
            reply = service.handle(command)
            write_frame(sink, reply.model_dump_json().encode(), limit)
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            service.close()
        except BaseException as cleanup:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Worker stream and cleanup failed", [primary, cleanup]
                ) from None
            raise
