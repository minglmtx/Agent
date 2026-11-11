"""Immutable exact transport bytes, not reconstructed model output or permission."""

from dataclasses import dataclass
from .generator_worker_protocol import (
    decode_command,
    decode_reply,
    GeneratorWorkerReply,
)


@dataclass(frozen=True)
class GeneratorWorkerExchange:
    command: bytes
    reply: bytes

    @property
    def decoded_reply(self) -> GeneratorWorkerReply:
        return decode_reply(decode_command(self.command), self.reply)
