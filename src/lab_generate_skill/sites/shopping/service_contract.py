"""Original Shopping files and five reserved local endpoints; no task authority."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.validation import Contract


class ShoppingPorts(Contract):
    web: int = Field(ge=1024, le=65535)
    database: int = Field(ge=1024, le=65535)
    redis: int = Field(ge=1024, le=65535)
    search: int = Field(ge=1024, le=65535)
    transport: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.model_dump().values())) != 5:
            raise ValueError("Five distinct reserved Shopping ports required")
        return self


class ShoppingServiceSpec(Contract):
    schema_version: Literal["shopping-services/1"] = "shopping-services/1"
    files: SiteFilesPlan
    ports: ShoppingPorts
    apptainer: Literal["/usr/bin/apptainer"] = "/usr/bin/apptainer"

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.ports.web}/"

    @property
    def control_root(self) -> str:
        return self.files.node_root + "/control"

    @property
    def runtime_root(self) -> str:
        return self.files.node_root + "/runtime"

    @property
    def snapshot_root(self) -> str:
        return self.files.node_root + "/snapshot"
