"""Length-delimited raw session frames; semantic request identity is caller-owned."""

import struct

HEADER_BYTES = 4


def frame(payload: bytes, limit: int) -> bytes:
    if type(payload) is not bytes:
        raise TypeError("Session payload must be exact bytes")
    if len(payload) > limit:
        raise ValueError("Session payload exceeds frozen limit")
    return struct.pack(">I", len(payload)) + payload


def frame_size(buffer: bytearray, limit: int) -> int | None:
    if len(buffer) < HEADER_BYTES:
        return None
    size: int = struct.unpack(">I", buffer[:HEADER_BYTES])[0]
    if size > limit:
        raise ValueError("Worker frame exceeds frozen limit")
    total = HEADER_BYTES + size
    if len(buffer) > total:
        raise ValueError("Worker returned unsolicited trailing frame bytes")
    return total
