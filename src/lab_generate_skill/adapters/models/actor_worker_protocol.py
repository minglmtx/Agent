"""Versioned single-session Actor wire data; no dynamic code/model fallback."""

import hashlib
from typing import Any, Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import (
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

MAX_WORKER_PACKET = 16 * 1024 * 1024
MAX_WORKER_COMMANDS = 10000
WorkerOperation = Literal["configure", "validate", "generate", "close"]


class ActorWorkerCommand(Contract):
    schema_version: Literal["actor-worker-command/1"] = "actor-worker-command/1"
    session_id: Identifier
    sequence: int = Field(ge=1, le=MAX_WORKER_COMMANDS)
    operation: WorkerOperation
    remaining_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    controller: ProcessIdentity | None = None
    artifact: ReleaseArtifact | None = None
    config: ActorEngineConfig | None = None
    installation: ReleaseInstallation | None = None
    request: ActorPrompt | None = None
    parameters: LocalActorParameters | None = None
    prepared_generation: Literal["actor-prepared-generation/1"] | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = dict(handler(self))
        if self.prepared_generation is None:
            result.pop("prepared_generation", None)
        return result

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.prepared_generation is not None and self.operation != "generate":
            raise ValueError("Only actual generation may consume prepared tokens")
        if (self.controller is not None) != (self.operation == "configure"):
            raise ValueError("Only configure must carry the original controller")
        if (self.installation is not None) != (self.operation == "configure"):
            raise ValueError("Only configure must carry its frozen installation")
        if (self.artifact is not None) != (self.operation == "configure") or (
            self.config is not None
        ) != (self.operation == "configure"):
            raise ValueError("Only configure must carry complete artifact/config")
        has_request = self.operation in ("validate", "generate")
        if (self.request is not None) != has_request or (
            self.parameters is not None
        ) != has_request:
            raise ValueError("Only validate/generate must carry request/parameters")
        if self.sequence == MAX_WORKER_COMMANDS and self.operation != "close":
            raise ValueError("Last command slot is reserved for close")
        if len(self.model_dump_json().encode()) > MAX_WORKER_PACKET:
            raise ValueError("Actor command exceeds wire budget")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ActorWorkerReply(Contract):
    schema_version: Literal["actor-worker-reply/1"] = "actor-worker-reply/1"
    session_id: Identifier
    sequence: int = Field(ge=1, le=MAX_WORKER_COMMANDS)
    operation: WorkerOperation
    command_sha256: Sha256
    status: Literal["ok", "input_rejected", "error"]
    output: LocalActorOutput | None = None
    error: RemoteError | None = None
    worker: ProcessIdentity | None = None
    owner_guard: ProcessOwnerGuard | None = None
    installed_sources: InstalledReleaseSources | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.owner_guard is not None) != (
            self.status == "ok" and self.operation == "configure"
        ):
            raise ValueError("Successful configure requires original process guard")
        if self.owner_guard is not None and self.owner_guard.worker != self.worker:
            raise ValueError("Guard differs from configured worker")
        if (self.installed_sources is not None) != (
            self.status == "ok" and self.operation == "configure"
        ):
            raise ValueError("Successful configure must return observed installation")
        if (self.worker is not None) != (
            self.status == "ok" and self.operation == "configure"
        ):
            raise ValueError(
                "Only successful configuration returns actual worker identity"
            )
        if (self.error is None) != (self.status == "ok"):
            raise ValueError("Worker error/status disagree")
        if (self.output is not None) != (
            self.status == "ok" and self.operation == "generate"
        ):
            raise ValueError("Only successful generation returns output")
        if self.status == "input_rejected" and self.operation not in (
            "validate",
            "generate",
        ):
            raise ValueError("Only inference preflight can reject token budget")
        if self.error is not None:
            validate_error_budget(self.error)
        if len(self.model_dump_json().encode()) > MAX_WORKER_PACKET:
            raise ValueError("Worker reply exceeds wire budget")
        return self


def decode_command(raw: bytes) -> ActorWorkerCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_WORKER_PACKET:
        raise ValueError("Invalid worker command bytes")
    json_object(raw)
    command = ActorWorkerCommand.model_validate_json(raw)
    if command.model_dump_json().encode() != raw:
        raise ValueError("Worker command must be canonical")
    return command


def decode_reply(command: ActorWorkerCommand, raw: bytes) -> ActorWorkerReply:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_WORKER_PACKET:
        raise ValueError("Invalid worker reply bytes")
    json_object(raw)
    reply = ActorWorkerReply.model_validate_json(raw)
    if reply.model_dump_json().encode() != raw:
        raise ValueError("Worker reply must be canonical")
    if (reply.session_id, reply.sequence, reply.operation, reply.command_sha256) != (
        command.session_id,
        command.sequence,
        command.operation,
        command.digest,
    ):
        raise ValueError("Worker reply differs from original command identity")
    if (
        reply.owner_guard is not None
        and reply.owner_guard.controller != command.controller
    ):
        raise ValueError("Worker guard differs from original controller")
    if reply.installed_sources is not None:
        assert command.installation is not None
        actual, expected = reply.installed_sources, command.installation
        if (actual.release_id, actual.manifest_sha256, actual.executable) != (
            expected.manifest.release_id,
            expected.manifest_ref.sha256,
            expected.python_executable,
        ):
            raise ValueError(
                "Worker observed installation differs from original command"
            )
    return reply


def validate_worker_output(
    output: LocalActorOutput, parameters: LocalActorParameters
) -> LocalActorOutput:
    output = LocalActorOutput.model_validate(output)
    if (
        not 1 <= output.prompt_tokens <= parameters.max_input_tokens
        or not 1 <= output.completion_tokens <= parameters.max_new_tokens
        or output.finish_reason not in ("stop", "length")
    ):
        raise ValueError("Worker output differs from frozen token limits")
    if (
        output.finish_reason == "length"
        and output.completion_tokens != parameters.max_new_tokens
    ):
        raise ValueError("Length termination must consume its output token budget")
    return output
