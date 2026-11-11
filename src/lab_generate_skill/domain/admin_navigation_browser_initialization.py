"""Declared local Admin navigation setup; references confer no permission."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import model_validator
from .validation import Contract, Sha256, NonEmptyText
from .evidence import EvidenceRef
from .browser_session import BrowserSessionSpec
from .task import PublicTask
from .state_scope import private_state_ref


class AdminNavigationInitialization(Contract):
    kind: Literal["admin_navigation"] = "admin_navigation"
    endpoint: NonEmptyText
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef
    native_contract_sha256: Sha256
    start_path: NonEmptyText

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
            raise ValueError("Original private Admin navigation endpoint required")
        for ref, schema in (
            (self.prepared_ref, "prepared-task/1"),
            (self.site_ref, "site-resource-started/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError("Private original Admin JSON required")
        path = self.start_path
        if (
            not path.startswith("/")
            or path.startswith("//")
            or any(c in path for c in ("?", "#", "\\"))
            or any(c.isspace() for c in path)
            or any(p in (".", "..") for p in path.split("/"))
        ):
            raise ValueError("Original declared local start path required")
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        if (
            task.identity.site,
            task.identity.family,
            task.identity.contract_version,
            task.identity.split,
        ) != ("shopping_admin", "page_navigation", 1, "train"):
            raise ValueError("Unsupported Admin navigation browser task family")
        actual, wanted = urlsplit(task.start_url), urlsplit(self.endpoint)
        if (
            (actual.scheme, actual.netloc, actual.path)
            != (wanted.scheme, wanted.netloc, "/admin" + self.start_path)
            or actual.query
            or actual.fragment
        ):
            raise ValueError(
                "Public task differs from original declared Admin navigation start"
            )
