"""Original acquired Map participant, complete files and existing record ports."""

from pathlib import Path
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.state_reader import (
    OriginalMapStateReader,
)
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.preparation_records import PreparationAuthority
from lab_generate_skill.sites.map.tasks.overlay_preparation_checks import (
    OverlayPreparationChecks,
)
from lab_generate_skill.sites.map.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_worker_inputs import MapWorkerInputs
from lab_generate_skill.sites.map.tasks.overlay_browser_binding import (
    OverlayBrowserChecks,
)


def map_original_state_reader(
    configuration: SiteWorkerConfiguration, instance: SiteInstanceStarted
) -> MapStateFileReader:
    access = OriginalMapSiteAccess(
        configuration, "controller", OriginalSiteAcquisitionReader(), None, instance
    )
    return OriginalMapStateReader(
        Path(configuration.files.workspace_root), access, access
    )


def map_prepared_browser_checks(
    store: EvidenceStore,
    configuration: SiteWorkerConfiguration,
    instance: SiteInstanceStarted,
) -> OverlayBrowserChecks:
    return OverlayBrowserChecks(
        store, map_original_state_reader(configuration, instance)
    )


def map_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
    configuration: SiteWorkerConfiguration,
    instance: SiteInstanceStarted,
) -> EvidencePreparationRecords:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    checks: NavigationPreparationChecks | OverlayPreparationChecks
    if configuration.site_id != "map":
        raise ValueError("Original Map preparation configuration required")
    if isinstance(configuration.map_inputs, MapNavigationWorkerInputs):
        checks = NavigationPreparationChecks(
            store, map_original_state_reader(configuration, instance)
        )
    elif isinstance(configuration.map_inputs, MapWorkerInputs):
        checks = OverlayPreparationChecks(
            store, map_original_state_reader(configuration, instance)
        )
    else:
        raise ValueError("Explicit supported Map task inputs required")
    return EvidencePreparationRecords(
        store,
        controls,
        bindings,
        checks,
        authority,
    )
