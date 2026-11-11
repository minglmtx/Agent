"""Selected Map facts on the common source qualification and Actor interfaces."""

from typing import Any
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.bootstrap.map_state_qualification import (
    map_state_qualifications,
)
from lab_generate_skill.bootstrap.map_initial_observation import (
    map_initial_observations,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlaySnapshot
from lab_generate_skill.sites.map.tasks.state_codec import (
    MapTaskStateCodec,
    MapSnapshot,
)
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from site_resource_fixtures import Case
from browser_resource_fixtures import ResourceCase
from qualified_source_native import QualifiedSource
from map_source_inputs import MapSourceInputs
from map_preparation_native import MapPreparation
from map_browser_capture_native import capture


class MapQualifiedSource(QualifiedSource):
    def __init__(
        self,
        c: Case,
        site: SiteHandle,
        inputs: MapSourceInputs,
        *,
        allowed_actions: tuple[str, ...],
        declared_endpoint: str | None = None,
    ) -> None:
        self.c, self.site = c, site
        self.native = MapPreparation(
            c,
            site.site.instance if declared_endpoint is None else None,
            inputs,
            allowed_actions=allowed_actions,
            declared_endpoint=declared_endpoint,
            actual_instance=lambda: site.site.instance,
        )
        self.records = map_state_qualifications(
            c.evidence, c.controls, self, c.spec, lambda: site.site
        )
        self.states = EvidenceStateRecords(c.evidence, c.controls, self)
        self.contexts = EvidenceContextRecords(c.evidence, c.controls, self)
        self.saved: dict[str, Any] = {}
        self.initialization: BrowserInitialization | None = None

    def parse_snapshot(self, result: SiteTaskResult) -> MapSnapshot:
        return MapTaskStateCodec(
            self.native.public.identity
        ).snapshot_type.model_validate_json(result.private_result)

    def initialize_session(
        self, b: ResourceCase, session: EvidenceBrowserSession, observed: dict[str, Any]
    ) -> None:
        self.initialization = b.spec.configuration.initialization
        pair = capture(
            b,
            session,
            (
                "map-navigation-initial"
                if isinstance(self.initialization, MapNavigationInitialization)
                else "map-initial-readiness"
            ),
        )
        self.initial_evidence = MapInitialEvidence(
            intent_ref=pair.intent_ref, result_ref=pair.result_ref
        )
        self.initial(b, observed)
        self.saved["map_initial_checks_ref"] = EvidenceRef.model_validate(
            observed["initial_checks_ref"]
        )
        self.saved["initial_selection"] = InitialObservationSelection(
            preparation=self.publication,
            browser_spec_ref=self.saved["browser_spec_ref"],
            browser_acquired_ref=EvidenceRef.model_validate(
                observed["browser_started_ref"]
            ),
        )

    def initial_records(
        self, authority: InitialObservationAuthority
    ) -> EvidenceInitialObservations:
        if self.initialization is None:
            raise ValueError("Original browser initialization has not been recorded")
        return map_initial_observations(
            self.c.evidence,
            self.c.controls,
            self.native.records,
            authority,
            self.initial_evidence,
            initialization=self.initialization,
        )
