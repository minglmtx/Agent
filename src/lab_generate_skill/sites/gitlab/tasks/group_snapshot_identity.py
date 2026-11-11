"""Original concrete Group snapshot identity; no restore or query rights."""

from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from .group_recovery import GroupRecoverySnapshot
from .native_snapshot import same_native_snapshot


def same_snapshot(
    request: SiteTaskRequest,
    snapshot: GroupRecoverySnapshot,
    original_ref: EvidenceRef | None,
) -> EvidenceRef:
    return same_native_snapshot(
        request,
        snapshot.request,
        snapshot.model_dump_json().encode(),
        snapshot.schema_version,
        original_ref,
        "Group",
    )
