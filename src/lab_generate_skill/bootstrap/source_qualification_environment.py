"""Original source snapshot/environment then one actual preparation publication."""

from lab_generate_skill.adapters.sites.source_qualification_state import (
    QualificationStateSelections,
)
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from .source_qualification_records import SourceQualificationRecords


def prepare_source(
    records: SourceQualificationRecords, qualifications: EvidenceStateQualifications
) -> None:
    p = records.progress
    if records.spec_ref is None:
        raise OwnershipConflict("Original complete source state declaration required")
    p.phase = "snapshot"
    records.request("snapshot", records.task_operation("snapshot"))
    if p.snapshot_ref is None:
        raise OwnershipConflict("Original source snapshot was not returned")
    op = records.task_operation("environment").model_copy(
        update={"recovery_ref": records.native.spec.token.recovery_ref}
    )
    selection = EnvironmentSelection(
        scope=records.owner.scope,
        spec_ref=records.spec_ref,
        site_spec_ref=records.put(records.native.spec, op),
        site_started_ref=records.put(records.site.site, op),
        snapshot_ref=p.snapshot_ref,
    )
    ref = records.put(selection, op)
    p.selections = QualificationStateSelections(selection, ref)
    p.environment_ref = qualifications.publish_environment(ref, op)
    p.references.append(p.environment_ref)
    p.environment = qualifications.load_environment(ref, p.environment_ref, op)
    if p.environment.checks.status != "pass":
        raise OwnershipConflict("Actual complete source environment is not qualified")
    p.phase = "preparing"
    records.request("prepare", records.task_operation("prepare"))
    records.publish_preparation()
    p.phase = "prepared"
