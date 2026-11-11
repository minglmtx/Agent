"""Mandatory original site/private storage admission; declarations grant no rights."""

from typing import Literal, Protocol
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest
from .lifecycle import OperationControl


class SitePrivateEvidenceAdmission(Protocol):
    def authorize(
        self,
        plan: SitePrivateEvidencePlan,
        context: SitePrivateEvidenceContext,
        request: SiteTaskRequest,
        phase: Literal["publish", "read"],
        control: OperationControl,
    ) -> None: ...


class SitePrivateArtifacts(Protocol):
    """Owned fixed storage assembly; no SQL/task or model dispatch rights."""

    def initialize(self, control: OperationControl) -> None: ...
    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None: ...
    def publish(
        self, request: SiteTaskRequest, raw: bytes, *, control: OperationControl
    ) -> SitePrivateEvidenceResult: ...
    def read(
        self,
        request: SiteTaskRequest,
        result: SitePrivateEvidenceResult,
        *,
        control: OperationControl,
    ) -> bytes: ...
    def stop_new_io(self) -> None: ...
