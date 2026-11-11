"""Site stream loop, original failure plus independent cleanup retained."""

from typing import BinaryIO
from lab_generate_skill.adapters.processes.stream_frames import read_frame, write_frame
from .worker_protocol import SiteWorkerCommand, MAX_PACKET, decode_command
from .worker_service import SiteService


def read_command(source: BinaryIO) -> SiteWorkerCommand | None:
    raw = read_frame(source, MAX_PACKET)
    return None if raw is None else decode_command(raw)


def serve(
    service: SiteService, source: BinaryIO, sink: BinaryIO, first: SiteWorkerCommand
) -> None:
    primary: BaseException | None = None
    pending: SiteWorkerCommand | None = first
    try:
        while not service.closed:
            command = pending if pending is not None else read_command(source)
            pending = None
            if command is None:
                break
            reply = service.handle(command)
            write_frame(sink, reply.model_dump_json().encode(), MAX_PACKET)
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            service.close()
        except BaseException as cleanup:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Site stream and cleanup failed", [primary, cleanup]
                ) from None
            raise
