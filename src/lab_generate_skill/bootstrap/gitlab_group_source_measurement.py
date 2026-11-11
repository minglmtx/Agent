"""Group actual prepared-account measurement through the shared one-observation port."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.sites.gitlab.tasks.group_reads import GroupStateReads
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from lab_generate_skill.sites.gitlab.tasks.group_source_initial import (
    CapturedGroupInitialChecks,
)
from .gitlab_group_capture import load_group_capture
from lab_generate_skill.sites.gitlab.tasks.group_browser_binding import (
    GroupBrowserChecks,
)
from .gitlab_group_browser_declarations import group_browser_declaration
from .gitlab_group_source_records import GroupSourceRecords, GroupSourceRecordPolicy
from .source_qualification_records import SourceQualificationRecords
from .source_qualification_measurement import SourceMeasurementBinding, measure_source
from .source_browser_assets import SourceBrowserAssets


def group_measurement_binding(
    public: PublicTask,
    endpoint: str,
    native_account_id: int,
    prepared_ref: EvidenceRef,
    site_ref: EvidenceRef,
    evidence: EvidenceReader,
) -> SourceMeasurementBinding:
    if not callable(getattr(evidence, "read", None)):
        raise TypeError("Original controlled Group evidence required")
    initialization = group_browser_declaration(
        public, endpoint, native_account_id, prepared_ref, site_ref
    )

    def checks(intent: EvidenceRef, result: EvidenceRef) -> InitialObservationChecks:
        return CapturedGroupInitialChecks(evidence, intent, result)

    return SourceMeasurementBinding(
        initialization,
        GroupBrowserChecks(evidence, load_group_capture),
        ("gitlab-page-health", "1"),
        checks,
    )


def measure_group_source(
    records: GroupSourceRecords,
    token: AllocationToken,
    assets: SourceBrowserAssets,
    *,
    operation_seconds: int,
) -> None:
    if not isinstance(records, GroupSourceRecords):
        raise TypeError("Original Group source records required")

    def declare(
        current: SourceQualificationRecords, public: PublicTask
    ) -> SourceMeasurementBinding:
        progress = records.progress
        if (
            current is not records
            or not isinstance(records.policy, GroupSourceRecordPolicy)
            or progress.publication is None
            or progress.prepare_request is None
            or progress.prepare_result is None
        ):
            raise OwnershipConflict("Original prepared Group source required")
        observed = GroupObserved.model_validate_json(
            progress.prepare_result.private_result
        )
        if (
            observed.request != progress.prepare_request
            or progress.prepare_result.request_sha256 != progress.prepare_request.digest
        ):
            raise OwnershipConflict("Group measurement changed original preparation")
        control = records.controls.bind(progress.prepare_request.operation)
        measured = GroupStateReads(records.owner.evidence, load_group_capture).native(
            observed.native, progress.prepare_request, control
        )
        site = records.site.site
        return group_measurement_binding(
            public,
            site.instance.endpoint,
            measured.state.user.id,
            progress.publication.prepared_ref,
            records.put(site, progress.prepare_request.operation),
            records.owner.evidence,
        )

    measure_source(records, token, assets, declare, operation_seconds=operation_seconds)
