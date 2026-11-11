"""Original Map measurement policy on the existing source acquisition algorithm."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.sites.map.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from .map_overlay_records import map_prepared_browser_checks
from .map_source_records import MapSourceRecords
from .source_qualification_records import SourceQualificationRecords
from .source_qualification_measurement import SourceMeasurementBinding, measure_source
from .source_browser_assets import SourceBrowserAssets as SourceBrowserAssets


def measure_map_source(
    records: MapSourceRecords,
    token: AllocationToken,
    assets: SourceBrowserAssets,
    *,
    operation_seconds: int = 180,
) -> None:
    def declare(
        current: SourceQualificationRecords, public: PublicTask
    ) -> SourceMeasurementBinding:
        p = records.progress
        if current is not records or p.publication is None or p.prepare_request is None:
            raise OwnershipConflict("Original prepared Map source required")
        site = records.site.site
        initialization = MapNavigationInitialization(
            endpoint=site.instance.endpoint,
            prepared_ref=p.publication.prepared_ref,
            site_ref=records.put(site, p.prepare_request.operation),
            native_contract_sha256=records.private.native_contract_ref.sha256,
        )

        def checks(
            intent: EvidenceRef, result: EvidenceRef
        ) -> InitialObservationChecks:
            p.initial_capture = MapInitialEvidence(intent_ref=intent, result_ref=result)
            return NavigationInitialObservationChecks(
                records.owner.evidence, p.initial_capture, initialization
            )

        return SourceMeasurementBinding(
            initialization,
            map_prepared_browser_checks(
                records.owner.evidence, records.native.spec.configuration, site.instance
            ),
            ("map-navigation-initial", "1"),
            checks,
        )

    measure_source(records, token, assets, declare, operation_seconds=operation_seconds)
