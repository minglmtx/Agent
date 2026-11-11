"""Fixed complete Group payload reads, never a native query or partial upgrade."""

from collections.abc import Callable
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..private_state_reads import GitlabPrivateReads
from .group_spec import GroupSpec
from .group_capture import GroupCapturedFacts
from .group_request import task_input
from .group_recovery import native_result


class GroupStateReads(GitlabPrivateReads):
    def __init__(
        self,
        store: EvidenceReader,
        loader: Callable[[bytes, GroupSpec], GroupCapturedFacts],
    ) -> None:
        super().__init__(store)
        self.loader = loader

    def native(
        self,
        descriptor: SitePrivateEvidenceResult,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> GroupCapturedFacts:
        descriptor = SitePrivateEvidenceResult.model_validate(descriptor)
        native_result(descriptor, request)
        raw = self.complete_bytes(descriptor.payload_ref, control)
        state = self.loader(raw, task_input(request))
        control.checkpoint()
        return state
