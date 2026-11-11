"""Bounded state facts only; no publication or execution permission."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.state_read import StateReadCommand
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_qualification import QualifiedResetChecks
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)

ENTRY = "lab_generate_skill.bootstrap.state_read_worker"
MAX_PACKET = 13 * 1024**2


class StateReadReply(Contract):
    schema_version: Literal["state-read-reply/1"] = "state-read-reply/1"
    request_sha256: Sha256
    worker: ProcessIdentity
    installed_sources: InstalledReleaseSources | None
    environment: EnvironmentBaseline | None
    reset: QualifiedResetChecks | None
    error: RemoteError | None
    read_count: int = Field(ge=0)
    body_read_count: int = Field(ge=0)
    unique_objects: int = Field(ge=0)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
            if self.environment is not None or self.reset is not None:
                raise ValueError("Failed state proof cannot carry successful facts")
        elif self.installed_sources is None or (
            (self.environment is None) == (self.reset is None)
        ):
            raise ValueError("Successful state proof requires one complete result")
        if max(self.body_read_count, self.unique_objects) > self.read_count:
            raise ValueError("State proof read counters are inconsistent")
        return self


def encode_command(command: StateReadCommand) -> bytes:
    raw = StateReadCommand.model_validate(command).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete state proof exceeds its bound")
    return raw


def decode_command(raw: bytes) -> StateReadCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Complete bounded state proof required")
    command = StateReadCommand.model_validate_json(raw)
    if encode_command(command) != raw:
        raise ValueError("State proof must retain canonical bytes")
    return command


def encode_reply(reply: StateReadReply) -> bytes:
    raw = StateReadReply.model_validate(reply).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete state proof reply exceeds its bound")
    return raw
