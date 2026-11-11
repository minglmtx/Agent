"""One original count exchange, never reconstructed from a returned number."""

from dataclasses import dataclass
from .actor_count_protocol import (
    ActorCountCommand,
    ActorCountReply,
    decode_worker_command,
    decode_count_reply,
)


@dataclass(frozen=True)
class ActorCountExchange:
    command: bytes
    reply: bytes

    @property
    def decoded_reply(self) -> ActorCountReply:
        command = decode_worker_command(self.command)
        if not isinstance(command, ActorCountCommand):
            raise ValueError("Original Actor count command required")
        return decode_count_reply(command, self.reply)
