"""Explicit original local endpoint; a declaration never grants a port or source."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import model_validator
from .validation import Contract, NonEmptyText, Sha256
from .state_scope import StateScope


class AdminNavigationOrigin(Contract):
    schema_version: Literal["admin-navigation-origin/1"] = "admin-navigation-origin/1"
    endpoint: NonEmptyText

    @model_validator(mode="after")
    def original(self) -> Self:
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or self.endpoint != f"http://127.0.0.1:{url.port}/admin"
        ):
            raise ValueError(
                "Exact original unprivileged Admin loopback origin required"
            )
        return self

    @property
    def web_port(self) -> int:
        port = urlsplit(self.endpoint).port
        assert port is not None
        return port


class AdminNavigationWorkerInputs(Contract):
    schema_version: Literal["admin-navigation-worker-inputs/1"] = (
        "admin-navigation-worker-inputs/1"
    )
    scope: StateScope
    native_contract_sha256: Sha256
    private_input_sha256: Sha256
    origin: AdminNavigationOrigin

    @model_validator(mode="after")
    def selected(self) -> Self:
        task = self.scope.task
        if (task.site, task.family, task.contract_version, task.split) != (
            "shopping_admin",
            "page_navigation",
            1,
            "train",
        ):
            raise ValueError("Selected train Admin navigation scope required")
        return self
