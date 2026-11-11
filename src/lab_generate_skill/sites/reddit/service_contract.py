"""Fixed original Postmill image and two private endpoints, without admission."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.validation import Contract

IMAGE_SHA256 = "96de2c4d52c51f9070c4d94869b8a0fd346c29905cccaa34d1af59a37f84fb02"
IMAGE_BYTES = 43292033024


def require_original_image(files: SiteFilesPlan) -> None:
    if (
        files.image.path,
        files.image.sha256,
        files.image.size_bytes,
        files.image.executable,
    ) != ("reddit.sif", IMAGE_SHA256, IMAGE_BYTES, False):
        raise ValueError("Pinned original Postmill image required")


class RedditPorts(Contract):
    web: int = Field(ge=1024, le=65535)
    database: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if self.web == self.database:
            raise ValueError("Two distinct reserved Reddit ports required")
        return self


class RedditServiceSpec(Contract):
    schema_version: Literal["reddit-services/1"] = "reddit-services/1"
    files: SiteFilesPlan
    ports: RedditPorts
    apptainer: Literal["/usr/bin/apptainer"] = "/usr/bin/apptainer"

    @model_validator(mode="after")
    def fixed_image(self) -> Self:
        require_original_image(self.files)
        return self

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

    @property
    def native_input_root(self) -> str:
        return self.files.node_root + "/native-input"
