"""Private instance service addresses, fixed independently of task semantics."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from .database_contract import AdminDatabaseLayout


class AdminPorts(Contract):
    schema_version: Literal["admin-ports/1"] = "admin-ports/1"
    web: int = Field(ge=1024, le=65535)
    database: int = Field(ge=1024, le=65535)
    redis: int = Field(ge=1024, le=65535)
    search: int = Field(ge=1024, le=65535)
    transport: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        values = (self.web, self.database, self.redis, self.search, self.transport)
        if len(set(values)) != 5:
            raise ValueError("Every service needs its own reserved loopback port")
        return self


class AdminServiceSpec(Contract):
    schema_version: Literal["admin-service-spec/1"] = "admin-service-spec/1"
    layout: AdminDatabaseLayout
    ports: AdminPorts

    @property
    def admin_url(self) -> str:
        return f"http://127.0.0.1:{self.ports.web}/admin"
