"""Fixed SSH resume contract on the shared once-only generation confirmer."""

from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from .ssh_key_lifecycle import SshKeyLifecycle
from .ssh_key_spec import SshKeySpec
from .ssh_key_state import SshKeyNativeState
from .ssh_key_recovery import SshKeyRecoverySnapshot, SshKeyRestored, SshKeyResumed
from .native_resume import GitlabNativeResume


def resumed(
    request: SiteResumeRequest,
    restored: SshKeyRestored,
    native: SitePrivateEvidenceResult,
    pins: tuple[NativeNamespaceIdentity, ...],
) -> str:
    return SshKeyResumed(
        request=request, restored=restored, native=native, original_pins=pins
    ).model_dump_json()


class SshKeyResume(
    GitlabNativeResume[
        SshKeySpec, SshKeyNativeState, SshKeyRecoverySnapshot, SshKeyRestored
    ]
):
    def __init__(self, lifecycle: SshKeyLifecycle) -> None:
        super().__init__(lifecycle, SshKeyRestored.model_validate_json, resumed)
