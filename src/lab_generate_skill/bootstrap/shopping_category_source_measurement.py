"""Category source declaration on the original measured browser lifecycle."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.sites.shopping.tasks.navigation_browser_checks import (
    CategoryNavigationBrowserChecks,
)
from lab_generate_skill.sites.shopping.tasks.navigation_input import (
    bind_category_navigation_inputs,
)
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from .shopping_category_initial_capture import CapturedCategoryNavigationInitialChecks
from .shopping_category_source_records import CategoryNavigationSourceRecordPolicy
from .source_browser_assets import SourceBrowserAssets
from .source_qualification_measurement import SourceMeasurementBinding, measure_source
from .source_qualification_records import SourceQualificationRecords


def category_navigation_measurement_binding(
    private: CategoryNavigationSpec,
    public: PublicTask,
    endpoint: str,
    prepared_ref: EvidenceRef,
    site_ref: EvidenceRef,
    evidence: EvidenceReader,
) -> SourceMeasurementBinding:
    private, public = CategoryNavigationSpec.model_validate(
        private
    ), PublicTask.model_validate(public)
    if not callable(getattr(evidence, "read", None)):
        raise TypeError("Original category evidence reader required")
    if (
        bind_category_navigation_inputs(
            private.original.model_dump(mode="json"),
            private.native_contract_ref,
            public,
        ).private_spec
        != private
    ):
        raise OwnershipConflict("Category measurement changed original private input")
    initialization = ShoppingCategoryInitialization(
        endpoint=endpoint,
        prepared_ref=prepared_ref,
        site_ref=site_ref,
        native_contract_sha256=private.native_contract_ref.sha256,
    )
    initialization.check_task(public)

    def checks(intent: EvidenceRef, result: EvidenceRef) -> InitialObservationChecks:
        return CapturedCategoryNavigationInitialChecks(evidence, intent, result)

    return SourceMeasurementBinding(
        initialization,
        CategoryNavigationBrowserChecks(),
        ("shopping-category-navigation-page", "1"),
        checks,
    )


def measure_category_navigation_source(
    records: SourceQualificationRecords,
    token: AllocationToken,
    assets: SourceBrowserAssets,
    *,
    operation_seconds: int,
) -> None:
    if not isinstance(records, SourceQualificationRecords) or not isinstance(
        records.policy, CategoryNavigationSourceRecordPolicy
    ):
        raise TypeError("Original category source records required")

    def declare(
        current: SourceQualificationRecords, public: PublicTask
    ) -> SourceMeasurementBinding:
        p, policy = records.progress, records.policy
        if (
            current is not records
            or not isinstance(policy, CategoryNavigationSourceRecordPolicy)
            or p.publication is None
            or p.prepare_request is None
        ):
            raise OwnershipConflict("Original prepared category source required")
        site = records.site.site
        return category_navigation_measurement_binding(
            policy.private,
            public,
            site.instance.endpoint,
            p.publication.prepared_ref,
            records.put(site, p.prepare_request.operation),
            records.owner.evidence,
        )

    measure_source(records, token, assets, declare, operation_seconds=operation_seconds)
