"""Admin source-only declared-start measurement on existing original ports.

Both original start declarations remain parameter data. No Actor, claim,
default permission, simulated page or predicted initial observation is supplied.
"""

from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_prepared_browser import (
    NavigationPreparedBrowserChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from .admin_navigation_source_records import (
    AdminNavigationSourceRecords,
    AdminNavigationSourceRecordPolicy,
)
from .source_browser_assets import SourceBrowserAssets
from .source_qualification_measurement import SourceMeasurementBinding, measure_source
from .source_qualification_records import SourceQualificationRecords
from .admin_navigation_initial_capture import CapturedAdminNavigationInitialChecks


def admin_navigation_measurement_binding(
    private: AdminNavigationSpec,
    public: PublicTask,
    endpoint: str,
    prepared_ref: EvidenceRef,
    site_ref: EvidenceRef,
    evidence: EvidenceReader,
) -> SourceMeasurementBinding:
    """Pure declared metadata. Original source/browser authority remains mandatory."""
    private, public = AdminNavigationSpec.model_validate(
        private
    ), PublicTask.model_validate(public)
    if not callable(getattr(evidence, "read", None)):
        raise TypeError("Original source evidence reader is mandatory")
    if public.identity != private.task:
        raise OwnershipConflict("Admin source measurement changed original task")
    initialization = AdminNavigationInitialization(
        endpoint=endpoint,
        prepared_ref=prepared_ref,
        site_ref=site_ref,
        native_contract_sha256=private.native_contract_ref.sha256,
        start_path=private.start_path,
    )
    initialization.check_task(public)

    def checks(intent: EvidenceRef, result: EvidenceRef) -> InitialObservationChecks:
        return CapturedAdminNavigationInitialChecks(evidence, intent, result)

    return SourceMeasurementBinding(
        initialization,
        NavigationPreparedBrowserChecks(),
        ("admin-navigation-page", "1"),
        checks,
    )


def measure_admin_navigation_source(
    records: AdminNavigationSourceRecords,
    token: AllocationToken,
    assets: SourceBrowserAssets,
    *,
    operation_seconds: int,
) -> None:
    if not isinstance(records, AdminNavigationSourceRecords):
        raise TypeError("Original Admin navigation source records required")

    def declare(
        current: SourceQualificationRecords, public: PublicTask
    ) -> SourceMeasurementBinding:
        p, policy = records.progress, records.policy
        if (
            current is not records
            or not isinstance(policy, AdminNavigationSourceRecordPolicy)
            or p.publication is None
            or p.prepare_request is None
        ):
            raise OwnershipConflict("Original prepared Admin source required")
        site = records.site.site
        return admin_navigation_measurement_binding(
            policy.private,
            public,
            site.instance.endpoint,
            p.publication.prepared_ref,
            records.put(site, p.prepare_request.operation),
            records.owner.evidence,
        )

    measure_source(records, token, assets, declare, operation_seconds=operation_seconds)
