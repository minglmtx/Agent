"""Original native Map layout and leased endpoints; no worker dispatch permission."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs


class MapPorts(Contract):
    web: int = Field(ge=1024, le=65535)
    search: int = Field(ge=1024, le=65535)
    car: int = Field(ge=1024, le=65535)
    bike: int = Field(ge=1024, le=65535)
    foot: int = Field(ge=1024, le=65535)
    tiles: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.model_dump().values())) != 6:
            raise ValueError("Six distinct original leased Map ports required")
        return self


class MapServiceSpec(Contract):
    schema_version: Literal["map-native-services/1"] = "map-native-services/1"
    inputs: MapRuntimeInputs
    ports: MapPorts
    apptainer: Literal["/usr/bin/apptainer"] = "/usr/bin/apptainer"

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.ports.web}/"

    def state_root(self, service: Literal["frontend", "search", "tiles"]) -> str:
        if service not in ("frontend", "search", "tiles"):
            raise ValueError("Explicit selected Map service state required")
        return str(PurePosixPath(self.inputs.files.state_root) / service)
