"""Fixed worker-local page probe and separately admitted parent read request."""

from typing import Any, Protocol, runtime_checkable
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from .lifecycle import OperationControl


class BrowserPageCollector(Protocol):
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        """Fixed trusted worker code only; no caller scripts or model access."""
        ...


class BrowserCaptureAuthority(Protocol):
    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        """Read original durable intent; verify acquired source, ownership and current phase."""
        ...


class ParentBrowserCapture(Protocol):
    @property
    def configuration(self) -> BrowserWorkerConfiguration: ...
    def capture_page(
        self,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        authority: BrowserCaptureAuthority,
        *,
        control: OperationControl,
    ) -> BrowserCaptureResult: ...


@runtime_checkable
class RawBrowserCapture(Protocol):
    @property
    def last_capture(self) -> BrowserCaptureResult | None: ...
    def capture_page(
        self, request: BrowserCaptureRequest, *, control: OperationControl
    ) -> BrowserCaptureResult: ...
