"""Child stream loop; consume exact bounded frames and always close its engine."""

from typing import BinaryIO
from lab_generate_skill.adapters.processes.stream_frames import read_frame
from lab_generate_skill.adapters.processes.framed_service import serve_framed
from .generator_service import GeneratorService
from .generator_worker_protocol import (
    MAX_WORKER_PACKET,
    decode_command,
    GeneratorWorkerCommand,
)


def read_command(source: BinaryIO) -> GeneratorWorkerCommand | None:
    raw = read_frame(source, MAX_WORKER_PACKET)
    return None if raw is None else decode_command(raw)


def serve(
    service: GeneratorService,
    source: BinaryIO,
    sink: BinaryIO,
    *,
    first: GeneratorWorkerCommand | None = None,
) -> None:
    serve_framed(
        service,
        source,
        sink,
        decode=decode_command,
        limit=MAX_WORKER_PACKET,
        first=first,
    )
