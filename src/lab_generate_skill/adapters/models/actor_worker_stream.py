"""Child stream loop; consume exact bounded frames and always close its engine."""

from typing import BinaryIO
from lab_generate_skill.adapters.processes.stream_frames import read_frame
from lab_generate_skill.adapters.processes.framed_service import (
    FramedService,
    serve_framed,
)
from .actor_service import ActorService
from .actor_worker_protocol import (
    MAX_WORKER_PACKET,
    ActorWorkerCommand,
    ActorWorkerReply,
)
from .actor_count_protocol import (
    ActorCountCommand,
    ActorCountReply,
    decode_worker_command,
)


def read_command(source: BinaryIO) -> ActorWorkerCommand | ActorCountCommand | None:
    raw = read_frame(source, MAX_WORKER_PACKET)
    return None if raw is None else decode_worker_command(raw)


def serve(
    service: ActorService,
    source: BinaryIO,
    sink: BinaryIO,
    *,
    first: ActorWorkerCommand | ActorCountCommand | None = None,
) -> None:
    framed: FramedService[
        ActorWorkerCommand | ActorCountCommand, ActorWorkerReply | ActorCountReply
    ] = service
    serve_framed(
        framed,
        source,
        sink,
        decode=decode_worker_command,
        limit=MAX_WORKER_PACKET,
        first=first,
    )
