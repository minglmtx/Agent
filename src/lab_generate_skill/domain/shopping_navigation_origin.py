"""Frozen category origin and input pins; no lease, source or execution right."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import model_validator
from .validation import Contract, NonEmptyText, Sha256
from .state_scope import StateScope


class ShoppingCategoryOrigin(Contract):
    schema_version: Literal["shopping-category-origin/1"] = "shopping-category-origin/1"
    endpoint: NonEmptyText

    @model_validator(mode="after")
    def original(self) -> Self:
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or not 1024 <= parsed.port <= 65535
            or self.endpoint != f"http://127.0.0.1:{parsed.port}/"
        ):
            raise ValueError("Exact original unprivileged Shopping root required")
        return self

    @property
    def web_port(self) -> int:
        value = urlsplit(self.endpoint).port
        assert value is not None
        return value


class ShoppingCategoryWorkerInputs(Contract):
    schema_version: Literal["shopping-category-worker-inputs/1"] = (
        "shopping-category-worker-inputs/1"
    )
    scope: StateScope
    native_contract_sha256: Sha256
    private_input_sha256: Sha256
    origin: ShoppingCategoryOrigin

    @model_validator(mode="after")
    def selected(self) -> Self:
        task = self.scope.task
        if (task.site, task.family, task.contract_version, task.split) != (
            "shopping",
            "page_navigation",
            1,
            "train",
        ):
            raise ValueError("Exact original train category scope required")
        return self
