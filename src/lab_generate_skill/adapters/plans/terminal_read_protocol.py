"""Bounded fixed terminal reader protocol on the existing read-scope primitive."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.terminal_read import (
    TerminalReadCommand,
    TerminalReadBodies,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)

ENTRY = "lab_generate_skill.bootstrap.terminal_read_worker"
MAX_PACKET = 13 * 1024**2


class TerminalReadReply(Contract):
    schema_version: Literal["terminal-read-reply/1"] = "terminal-read-reply/1"
    request_sha256: Sha256
    worker: ProcessIdentity
    installed_sources: InstalledReleaseSources | None
    bodies: TerminalReadBodies | None
    error: RemoteError | None
    read_count: int = Field(ge=0)
    body_read_count: int = Field(ge=0)
    unique_objects: int = Field(ge=0)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
            if self.bodies is not None:
                raise ValueError(
                    "Failed terminal proof cannot return successful bodies"
                )
        elif self.installed_sources is None or self.bodies is None:
            raise ValueError(
                "Successful terminal proof needs installed complete bodies"
            )
        if not self.unique_objects <= self.body_read_count <= self.read_count:
            raise ValueError("Inconsistent terminal read counters")
        return self


def encode_command(command: TerminalReadCommand) -> bytes:
    raw = TerminalReadCommand.model_validate(command).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete terminal command exceeds bound")
    return raw


def decode_command(raw: bytes) -> TerminalReadCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Complete bounded terminal command required")
    command = TerminalReadCommand.model_validate_json(raw)
    if encode_command(command) != raw:
        raise ValueError("Canonical terminal command required")
    return command


def encode_reply(reply: TerminalReadReply) -> bytes:
    raw = TerminalReadReply.model_validate(reply).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete terminal reply exceeds bound")
    return raw
