"""Bind per-command permissions to the one acknowledged worker acquisition."""

from typing import Literal
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.site_resources import SiteResourceAuthority
from lab_generate_skill.ports.lifecycle import OperationControl


class BoundSiteAuthority:
    def __init__(
        self,
        spec: SiteResourceSpec,
        acquisition: OperationContext,
        authority: SiteResourceAuthority,
    ) -> None:
        self.spec, self.acquisition, self.authority = spec, acquisition, authority
        self.acquired_ref: EvidenceRef | None = None

    def verify(
        self,
        configuration: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if configuration != self.spec.configuration:
            raise OwnershipConflict(
                "Site command changed frozen resource configuration"
            )
        self.spec.check_operation(
            operation, "cleanup" if phase == "close" else "execute"
        )
        if phase != "close" and operation != self.acquisition:
            raise OwnershipConflict("Site command changed original acquisition")
        if phase == "start" and self.acquired_ref is None:
            raise OwnershipConflict(
                "Site effects require acknowledged worker acquisition"
            )
        self.authority.verify(configuration, phase, operation, control)

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        if configuration != self.spec.configuration or self.acquired_ref is None:
            raise OwnershipConflict(
                "Task requires original acknowledged site acquisition"
            )
        request.check_site(configuration)
        self.authority.verify_task(configuration, request, control)
