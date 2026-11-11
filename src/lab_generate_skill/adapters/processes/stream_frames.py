"""Shared bounded blocking frames inside externally supervised role workers."""

import struct
from typing import BinaryIO
from .framing import frame


def _read_exact(source: BinaryIO, size: int, *, allow_eof: bool = False) -> bytes:
    data = bytearray()
    while len(data) < size:
        block = source.read(size - len(data))
        if not block:
            if allow_eof and not data:
                return b""
            raise EOFError("Worker input frame truncated")
        data.extend(block)
    return bytes(data)


def read_frame(source: BinaryIO, limit: int) -> bytes | None:
    prefix = _read_exact(source, 4, allow_eof=True)
    if not prefix:
        return None
    size: int = struct.unpack(">I", prefix)[0]
    if not 0 < size <= limit:
        raise ValueError("Worker input frame exceeds budget")
    return _read_exact(source, size)


def write_frame(sink: BinaryIO, payload: bytes, limit: int) -> None:
    view = memoryview(frame(payload, limit))
    while view:
        written = sink.write(view)
        if written is None or written <= 0:
            raise BrokenPipeError("Worker output made no progress")
        view = view[written:]
    sink.flush()
