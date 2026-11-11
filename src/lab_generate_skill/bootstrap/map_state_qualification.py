"""Fixed original Map context, full-file reader and existing qualification port."""

from collections.abc import Callable
from .deferred_state_records import DeferredStateQualificationChecks
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.state_qualification import StateQualificationAuthority
from lab_generate_skill.ports.state_qualification import StateQualificationChecks
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)
from lab_generate_skill.adapters.map_artifacts.state_graph_checks import (
    MapStateGraphChecks,
)
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from .map_overlay_records import map_original_state_reader


def map_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
    site: SiteResourceSpec,
    started: SiteResourceStarted | Callable[[], SiteResourceStarted],
    *,
    state_inputs: MapStateInputsTransport | None = None,
) -> EvidenceStateQualifications:
    configured = site.configuration.map_inputs
    if state_inputs is not None and (
        not isinstance(state_inputs, MapStateInputsTransport)
        or configured is None
        or state_inputs.task != configured.scope.task
    ):
        raise ValueError("Map state input transport changed configured task")

    def original_checks(actual: SiteResourceStarted) -> StateQualificationChecks:
        files = map_original_state_reader(site.configuration, actual.instance)
        if state_inputs is not None:
            return MapStateGraphChecks(state_inputs, files, site, actual)
        return OverlayStateChecks(
            store,
            files,
            site,
            actual,
        )

    return EvidenceStateQualifications(
        store,
        controls,
        DeferredStateQualificationChecks(
            lambda: original_checks(started() if callable(started) else started)
        ),
        authority,
    )
