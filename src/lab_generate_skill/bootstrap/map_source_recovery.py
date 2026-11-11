"""Original Map recovery codecs; shared ports keep ownership and once semantics."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.sites.map.tasks.navigation_recovery import (
    NavigationRestored,
    NavigationSnapshot,
    NavigationResumed,
)
from .map_source_records import MapSourceRecords
from .source_qualification_recovery import (
    close_source_browser as close_map_source_browser,
    restore_source,
)


class MapSourceRecoveryChecks:
    def restore(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        snapshot_ref: EvidenceRef,
        snapshot: bytes,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        restored = NavigationRestored.model_validate_json(result.private_result)
        original = NavigationSnapshot.model_validate_json(snapshot)
        if restored.request != request or restored.snapshot != original:
            raise OwnershipConflict("Source restore returned another original snapshot")

    def resume(
        self,
        request: SiteResumeRequest,
        result: SiteResumeResult,
        restored: SiteTaskResult,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        resumed = NavigationResumed.model_validate_json(result.private_result)
        original = NavigationRestored.model_validate_json(restored.private_result)
        if resumed.request != request or resumed.restored != original:
            raise OwnershipConflict(
                "Source frontend resume changed original restore lineage"
            )


def restore_map_source(
    records: MapSourceRecords, qualifications: EvidenceStateQualifications
) -> None:
    restore_source(records, qualifications, MapSourceRecoveryChecks())


__all__ = ["close_map_source_browser", "restore_map_source", "MapSourceRecoveryChecks"]
