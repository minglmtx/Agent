"""Prepared selected native query file identity; not resource admission."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .map_services import MapServiceSpec
from .release import ReleaseFile


class MapDatabaseExport(Contract):
    schema_version: Literal["map-database-export/1"] = "map-database-export/1"
    spec: MapServiceSpec
    label: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    program: ReleaseFile
    max_output_bytes: int = Field(ge=1, le=2 * 1024**4)

    @model_validator(mode="after")
    def fixed_program(self) -> Self:
        if (
            self.program.path != "reference.rb"
            or self.program.executable
            or not 0 < self.program.size_bytes <= 65536
        ):
            raise ValueError("Bounded fixed native reference program pin required")
        return self

    @property
    def directory_name(self) -> str:
        return "native-reference-" + self.label

    @property
    def host_directory(self) -> str:
        return str(
            PurePosixPath(self.spec.state_root("frontend")) / self.directory_name
        )

    @property
    def container_program(self) -> str:
        return "/state/" + self.directory_name + "/reference.rb"

    @property
    def output_name(self) -> str:
        return "osm-expanded-" + self.label + ".json"
