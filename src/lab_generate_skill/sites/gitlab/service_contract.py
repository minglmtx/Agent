"""Original private GitLab layout and two distinct local service endpoints."""

from typing import Literal, Self
import re
from pydantic import Field, field_validator, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_files import SiteFilesPlan


def peer_user(value: str) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,31}", value) is None
    ):
        raise ValueError("Explicit original native peer user required")
    return value


class GitlabPorts(Contract):
    web: int = Field(ge=1024, le=65535)
    metrics: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if self.web == self.metrics:
            raise ValueError("Two distinct original GitLab ports required")
        return self


class GitlabServiceSpec(Contract):
    schema_version: Literal["gitlab-services/1"] = "gitlab-services/1"
    files: SiteFilesPlan
    ports: GitlabPorts
    database_peer_user: str = Field(pattern=r"\A[A-Za-z_][A-Za-z0-9_-]{0,31}\z")
    apptainer: Literal["/usr/bin/apptainer"] = "/usr/bin/apptainer"

    @field_validator("database_peer_user")
    @classmethod
    def checked_peer_user(cls, value: str) -> str:
        return peer_user(value)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.ports.web}/"

    @property
    def control_root(self) -> str:
        return self.files.node_root + "/control"

    @property
    def snapshot_root(self) -> str:
        return self.files.node_root + "/snapshot"
