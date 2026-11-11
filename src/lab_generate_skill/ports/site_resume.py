"""Mandatory actual source/instance/writer/lease admission for explicit resume."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from .lifecycle import OperationControl


class SiteResumeAuthority(Protocol):
    def verify_resume(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        """Read exact durable intent/restore and verify original acquired resource.

        Also require actual frontend recovery coverage, browser closure, sole
        writer and original lease. Serialized descriptors alone grant no rights.
        """
        ...


class ParentSiteResume(Protocol):
    @property
    def configuration(self) -> SiteWorkerConfiguration: ...
    def resume_frontend(
        self,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        authority: SiteResumeAuthority,
        *,
        control: OperationControl,
    ) -> SiteResumeResult: ...


@runtime_checkable
class SiteResume(Protocol):
    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult: ...
