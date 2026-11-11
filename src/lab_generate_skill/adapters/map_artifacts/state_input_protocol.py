"""Fixed Map immutable-input packet; no native-file or state-proof result."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.map_state_inputs import (
    MapStateInputsCommand,
    MapStateInputBodies,
)
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)

ENTRY = "lab_generate_skill.bootstrap.map_state_inputs_worker"
MAX_PACKET = 13 * 1024**2


class MapStateInputsReply(Contract):
    schema_version: Literal["map-state-inputs-reply/1"] = "map-state-inputs-reply/1"
    request_sha256: Sha256
    action: Literal["inputs", "check"]
    worker: ProcessIdentity
    installed_sources: InstalledReleaseSources | None
    bodies: MapStateInputBodies | None
    error: RemoteError | None
    read_count: int = Field(ge=0)
    body_read_count: int = Field(ge=0)
    unique_objects: int = Field(ge=0)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
            if self.bodies is not None:
                raise ValueError("Failed Map input read cannot return bodies")
        elif self.installed_sources is None or (self.bodies is not None) != (
            self.action == "inputs"
        ):
            raise ValueError("Complete original Map input/check reply required")
        if max(self.body_read_count, self.unique_objects) > self.read_count:
            raise ValueError("Map input read counters are inconsistent")
        return self


def encode_command(command: MapStateInputsCommand) -> bytes:
    raw = MapStateInputsCommand.model_validate(command).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Map input command exceeds packet bound")
    return raw


def decode_command(raw: bytes) -> MapStateInputsCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Complete bounded Map input command required")
    command = MapStateInputsCommand.model_validate_json(raw)
    if encode_command(command) != raw:
        raise ValueError("Canonical original Map input command required")
    return command


def encode_reply(reply: MapStateInputsReply) -> bytes:
    raw = MapStateInputsReply.model_validate(reply).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete Map input reply exceeds packet bound")
    return raw
