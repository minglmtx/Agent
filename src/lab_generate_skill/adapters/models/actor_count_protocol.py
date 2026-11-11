"""Read-only count frames on the original ordered Actor worker channel.

Generation command/reply schemas and saved exchanges remain unchanged. No
configure fields, dynamic dispatch, inference output or source permissions here.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256
from lab_generate_skill.domain.actor_context_count import ActorTokenCount, digest
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from .actor_worker_protocol import (
    MAX_WORKER_PACKET,
    MAX_WORKER_COMMANDS,
    ActorWorkerCommand,
    decode_command,
)


class ActorCountCommand(Contract):
    schema_version: Literal["actor-context-count-command/1"] = (
        "actor-context-count-command/1"
    )
    session_id: Identifier
    sequence: int = Field(ge=2, lt=MAX_WORKER_COMMANDS)
    operation: Literal["measure"] = "measure"
    remaining_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    request: ActorPrompt
    parameters: LocalActorParameters

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.model_dump_json().encode()) > MAX_WORKER_PACKET:
            raise ValueError("Actor count command exceeds wire budget")
        return self

    @property
    def digest(self) -> str:
        return digest(self)


class ActorCountReply(Contract):
    schema_version: Literal["actor-context-count-reply/1"] = (
        "actor-context-count-reply/1"
    )
    session_id: Identifier
    sequence: int = Field(ge=2, lt=MAX_WORKER_COMMANDS)
    operation: Literal["measure"] = "measure"
    command_sha256: Sha256
    status: Literal["ok", "error"]
    measurement: ActorTokenCount | None = None
    error: RemoteError | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.measurement is not None) != (self.status == "ok") or (
            self.error is not None
        ) != (self.status == "error"):
            raise ValueError("Count reply status/result/error disagree")
        if self.error is not None:
            validate_error_budget(self.error)
        if len(self.model_dump_json().encode()) > MAX_WORKER_PACKET:
            raise ValueError("Actor count reply exceeds wire budget")
        return self


def decode_worker_command(raw: bytes) -> ActorWorkerCommand | ActorCountCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_WORKER_PACKET:
        raise ValueError("Invalid Actor worker frame bytes")
    data = json_object(raw)
    if data.get("schema_version") == "actor-worker-command/1":
        return decode_command(raw)
    if data.get("schema_version") != "actor-context-count-command/1":
        raise ValueError("Unsupported explicit Actor worker command schema")
    command = ActorCountCommand.model_validate_json(raw)
    if command.model_dump_json().encode() != raw:
        raise ValueError("Actor count command must be canonical")
    return command


def decode_count_reply(command: ActorCountCommand, raw: bytes) -> ActorCountReply:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_WORKER_PACKET:
        raise ValueError("Invalid count reply bytes")
    json_object(raw)
    reply = ActorCountReply.model_validate_json(raw)
    if reply.model_dump_json().encode() != raw:
        raise ValueError("Actor count reply must be canonical")
    if (reply.session_id, reply.sequence, reply.command_sha256) != (
        command.session_id,
        command.sequence,
        command.digest,
    ):
        raise ValueError("Count reply differs from original command")
    return reply
