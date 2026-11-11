"""Pure SSH-key input/snapshot identity checks; no task execution authority."""

from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from .ssh_key_spec import SshKeySpec
from .ssh_key_recovery import SshKeyRecoverySnapshot
from .native_snapshot import same_native_snapshot


def task_input(request: SiteTaskRequest) -> SshKeySpec:
    value = SshKeySpec.model_validate_json(request.private_input)
    if value.model_dump_json() != request.private_input or value.task != request.task:
        raise OwnershipConflict("SSH-key private input changed original canonical task")
    return value


def same_snapshot(
    request: SiteTaskRequest,
    snapshot: SshKeyRecoverySnapshot,
    original_ref: EvidenceRef | None,
) -> EvidenceRef:
    return same_native_snapshot(
        request,
        snapshot.request,
        snapshot.model_dump_json().encode(),
        snapshot.schema_version,
        original_ref,
        "SSH-key",
    )
