"""Finite SFT wire over the shared process transport; no dynamic code selection."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

from lab_generate_skill.domain.training_worker_call import (
    TrainingWorkerCommand as TrainingWorkerCommand,
    MAX_PACKET as MAX_PACKET,
    Operation as Operation,
)


class TrainingWorkerReply(Contract):
    schema_version: Literal["sft-worker-reply/1"] = "sft-worker-reply/1"
    session_id: Identifier
    sequence: int = Field(ge=1, le=3)
    operation: Operation
    command_sha256: Sha256
    status: Literal["ok", "error"]
    guard: ProcessOwnerGuard | None = None
    installed: InstalledReleaseSources | None = None
    execution_ref: EvidenceRef | None = None
    error: RemoteError | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        configured = self.status == "ok" and self.operation == "configure"
        if (
            (self.guard is not None) != configured
            or (self.installed is not None) != configured
            or (self.error is None) != (self.status == "ok")
        ):
            raise ValueError("Training reply status/guard/installation/error disagree")
        if self.execution_ref is not None:
            private_state_ref(self.execution_ref, "sft-native-execution/1")
            if self.operation != "train":
                raise ValueError("Only training can report native execution evidence")
        if (
            self.status == "ok"
            and self.operation == "train"
            and self.execution_ref is None
        ):
            raise ValueError(
                "Successful training requires exact original return evidence"
            )
        if self.error is not None:
            validate_error_budget(self.error)
        if len(self.model_dump_json().encode()) > MAX_PACKET:
            raise ValueError("Training reply exceeds wire bound")
        return self


def decode_command(raw: bytes) -> TrainingWorkerCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Invalid training command bytes")
    json_object(raw)
    result = TrainingWorkerCommand.model_validate_json(raw)
    if result.model_dump_json().encode() != raw:
        raise ValueError("Training command must be canonical complete bytes")
    return result


def decode_reply(command: TrainingWorkerCommand, raw: bytes) -> TrainingWorkerReply:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Invalid training reply bytes")
    json_object(raw)
    result = TrainingWorkerReply.model_validate_json(raw)
    if result.model_dump_json().encode() != raw or (
        result.session_id,
        result.sequence,
        result.operation,
        result.command_sha256,
    ) != (command.session_id, command.sequence, command.operation, command.digest):
        raise ValueError("Training reply changed canonical command identity")
    if result.guard is not None and result.guard.controller != command.controller:
        raise ValueError("Training reply changed original controller")
    if result.installed is not None:
        assert command.configuration is not None
        expected = command.configuration.installation
        if (
            result.installed.release_id,
            result.installed.manifest_sha256,
            result.installed.executable,
        ) != (
            expected.manifest.release_id,
            expected.manifest_ref.sha256,
            expected.python_executable,
        ):
            raise ValueError("Training reply changed actual installation")
    return result
