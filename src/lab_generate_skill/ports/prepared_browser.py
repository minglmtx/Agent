"""Selected semantic join; the original resource/preparation authority stays mandatory."""

from typing import Protocol
from dataclasses import dataclass
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


@dataclass(frozen=True)
class PreparedBrowserInputs:
    binding: object
    browser: BrowserResourceSpec
    request: SiteTaskRequest
    environment: EnvironmentBaseline
    checked_by: object | None
    site_bodies: tuple[tuple[EvidenceRef, bytes], ...]


class PreparedBrowserInputScope(Protocol):
    prepared_browser: PreparedBrowserInputs | None

    def check(self, op: OperationContext, control: OperationControl) -> None: ...


class PreparedBrowserTaskChecks(Protocol):
    def check(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        request: SiteTaskRequest,
        initialization: BrowserInitialization,
        control: OperationControl,
    ) -> None: ...
