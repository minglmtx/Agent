"""Fixed SSH family contracts on the shared original GitLab task engine."""

from collections.abc import Callable
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from ..instance import GitlabInstance
from ..services import GitlabGeneration
from ..snapshot import GitlabSnapshot, GitlabInventory
from ..ssh_native_reader import GitlabSshNativeReader
from .ssh_key_spec import SshKeySpec
from .ssh_key_state import SshKeyNativeState
from .ssh_key_rules import preserved
from .ssh_key_admission import task_input
from .ssh_key_recovery import SshKeyRecoverySnapshot, SshKeyObserved, SshKeyRestored
from .native_lifecycle import GitlabNativeLifecycle


def same_ssh_state(before: SshKeyNativeState, after: SshKeyNativeState) -> bool:
    return preserved(before, after) and before.keys == after.keys


def baseline(spec: SshKeySpec, state: SshKeyNativeState) -> None:
    if state.task != spec.task:
        raise OwnershipConflict("Native SSH state changed original task")


def snapshot(
    request: SiteTaskRequest, state: GitlabSnapshot, native: SitePrivateEvidenceResult
) -> SshKeyRecoverySnapshot:
    return SshKeyRecoverySnapshot(request=request, state=state, native_before=native)


def observed(
    request: SiteTaskRequest,
    saved: SshKeyRecoverySnapshot,
    native: SitePrivateEvidenceResult,
) -> str:
    return SshKeyObserved(
        request=request, snapshot=saved, native=native
    ).model_dump_json()


def restored(
    request: SiteTaskRequest,
    saved: SshKeyRecoverySnapshot,
    generation: GitlabGeneration,
    inventory: GitlabInventory,
    native: SitePrivateEvidenceResult,
) -> str:
    assert generation.quiescence is not None
    return SshKeyRestored(
        request=request,
        snapshot=saved,
        stopped=generation.quiescence,
        gitaly_term=generation.gitaly_term,
        workhorse_terms=generation.workhorse_terms,
        inventory=inventory,
        native=native,
    ).model_dump_json()


class SshKeyLifecycle(
    GitlabNativeLifecycle[SshKeySpec, SshKeyNativeState, SshKeyRecoverySnapshot]
):
    def __init__(
        self,
        instance: GitlabInstance,
        reader: GitlabSshNativeReader,
        username: Callable[[OperationControl], str],
        artifacts: SitePrivateArtifacts,
    ) -> None:
        super().__init__(
            instance,
            reader,
            username,
            artifacts,
            label="SSH-key",
            collector="gitlab-profile-ssh-key",
            inputs=task_input,
            same_state=same_ssh_state,
            validate_baseline=baseline,
            snapshot=snapshot,
            observed=observed,
            restored=restored,
        )
