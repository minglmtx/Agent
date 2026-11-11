"""Fixed SSH state adapter over shared original evidence reads."""

from typing import Protocol
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .private_state_reads import GitlabPrivateReads
from .tasks.ssh_key_spec import SshKeySpec
from .tasks.ssh_key_state import SshKeyNativeState
from .tasks.ssh_key_admission import task_input
from .tasks.ssh_key_recovery import native_result


class NativeStateLoader(Protocol):
    def __call__(self, raw: bytes, spec: SshKeySpec) -> SshKeyNativeState: ...
class GitlabStateReads(GitlabPrivateReads):
    def __init__(self, store: EvidenceReader, loader: NativeStateLoader) -> None:
        super().__init__(store)
        self.loader = loader

    def native(
        self,
        descriptor: SitePrivateEvidenceResult,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> SshKeyNativeState:
        descriptor = SitePrivateEvidenceResult.model_validate(descriptor)
        native_result(descriptor, request)
        ref = descriptor.payload_ref
        raw = self.complete_bytes(ref, control)
        state = self.loader(raw, task_input(request))
        control.checkpoint()
        return state
