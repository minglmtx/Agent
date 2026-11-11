"""Immutable exact transport bytes, not reconstructed model output or permission."""

from dataclasses import dataclass
from .actor_worker_protocol import (
    decode_command,
    decode_reply,
    ActorWorkerReply,
)


@dataclass(frozen=True)
class ActorWorkerExchange:
    command: bytes
    reply: bytes

    @property
    def decoded_reply(self) -> ActorWorkerReply:
        return decode_reply(decode_command(self.command), self.reply)
