"""Group's concrete resume model on the shared once-only generation confirmer."""

from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from .native_resume import GitlabNativeResume
from .group_lifecycle import GroupLifecycle
from .group_spec import GroupSpec
from .group_capture import GroupCapturedFacts
from .group_recovery import GroupRecoverySnapshot, GroupRestored, GroupResumed


def resumed(
    request: SiteResumeRequest,
    restored: GroupRestored,
    native: SitePrivateEvidenceResult,
    pins: tuple[NativeNamespaceIdentity, ...],
) -> str:
    return GroupResumed(
        request=request, restored=restored, native=native, original_pins=pins
    ).model_dump_json()


class GroupResume(
    GitlabNativeResume[
        GroupSpec, GroupCapturedFacts, GroupRecoverySnapshot, GroupRestored
    ]
):
    def __init__(self, lifecycle: GroupLifecycle) -> None:
        super().__init__(lifecycle, GroupRestored.model_validate_json, resumed)
