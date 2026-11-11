"""Exact allocated category origin and original prepared facts; no permission."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from .validation import Contract, Sha256
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .browser_session import BrowserSessionSpec
from .task import PublicTask


class ShoppingCategoryInitialization(Contract):
    kind: Literal["shopping_category_navigation"] = "shopping_category_navigation"
    endpoint: str = Field(min_length=1, max_length=4096)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef
    native_contract_sha256: Sha256

    @model_validator(mode="after")
    def original_inputs(self) -> Self:
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or self.endpoint != f"http://127.0.0.1:{url.port}/"
        ):
            raise ValueError("Original allocated Shopping category root required")
        for ref, schema in (
            (self.prepared_ref, "prepared-task/1"),
            (self.site_ref, "site-resource-started/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError("Original private category preparation/site required")
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        task = PublicTask.model_validate(task)
        identity = task.identity
        actual, root = urlsplit(task.start_url), urlsplit(self.endpoint)
        if (
            (identity.site, identity.family, identity.contract_version, identity.split)
            != ("shopping", "page_navigation", 1, "train")
            or (actual.scheme, actual.netloc) != (root.scheme, root.netloc)
            or not actual.path.startswith("/")
            or any(c in task.start_url for c in ("\\", "\0", "\r", "\n", "\t"))
        ):
            raise ValueError(
                "Original public category start and allocated origin required"
            )
