"""Original site/task collector authority and fixed worker capability."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from .lifecycle import OperationControl


class SiteCaptureAuthority(Protocol):
    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        """Read exact durable intent; verify original acquired resource, live
        source/binding, collector/version, snapshot and exclusive attempt state.
        Read-only does not grant source rights or permit unknown replay.
        """
        ...


class ParentSiteCapture(Protocol):
    @property
    def configuration(self) -> SiteWorkerConfiguration: ...
    def capture_task(
        self,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        authority: SiteCaptureAuthority,
        *,
        control: OperationControl,
    ) -> SiteTaskResult: ...


@runtime_checkable
class SiteCapture(Protocol):
    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult: ...
