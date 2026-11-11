"""Explicit selected navigation setup; references and declarations grant no rights."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from .validation import Contract, NonEmptyText, Sha256
from .evidence import EvidenceRef
from .browser_session import BrowserSessionSpec
from .task import PublicTask
from .map_browser_initialization import original_map_initial_inputs
from .map_navigation_scope import check_page_navigation_scope


class MapNavigationInitialization(Contract):
    kind: Literal["map_native_navigation"] = "map_native_navigation"
    endpoint: NonEmptyText = Field(max_length=4096)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef
    native_contract_sha256: Sha256

    @model_validator(mode="after")
    def original_inputs(self) -> Self:
        original_map_initial_inputs(self.endpoint, self.prepared_ref, self.site_ref)
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        task = PublicTask.model_validate(task)
        check_page_navigation_scope(task.identity, self.native_contract_sha256)
        actual, root = urlsplit(task.start_url), urlsplit(self.endpoint)
        if (actual.scheme, actual.netloc) != (root.scheme, root.netloc):
            raise ValueError("Original allocated navigation origin required")
