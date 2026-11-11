"""Bounded binary stream for a single browser service, with independent cleanup."""

from typing import BinaryIO
from lab_generate_skill.adapters.processes.stream_frames import read_frame, write_frame
from .worker_protocol import MAX_PACKET, BrowserWorkerCommand, decode_command
from .worker_service import BrowserService


def read_command(source: BinaryIO) -> BrowserWorkerCommand | None:
    raw = read_frame(source, MAX_PACKET)
    return None if raw is None else decode_command(raw)


def serve(
    service: BrowserService,
    source: BinaryIO,
    sink: BinaryIO,
    first: BrowserWorkerCommand,
) -> None:
    primary: BaseException | None = None
    pending: BrowserWorkerCommand | None = first
    try:
        while not service.closed:
            command = pending if pending is not None else read_command(source)
            pending = None
            if command is None:
                break
            reply = service.handle(command)
            write_frame(sink, reply.model_dump_json().encode(), MAX_PACKET)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            service.close()
        except BaseException as cleanup:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Browser stream and cleanup failed", [primary, cleanup]
                ) from None
            raise
