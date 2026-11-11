"""Fixed selected Map collection assembly; constructors do no file/native I/O."""

from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.ports.browser_storage import BrowserStorageGuard
from lab_generate_skill.ports.lifecycle import Clock
from lab_generate_skill.adapters.browsergym.collection_control import (
    OriginalMapCollectionControl,
)
from lab_generate_skill.adapters.browsergym.storage_original import (
    OriginalBrowserAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.browser_access import (
    OriginalMapBrowserAccess,
)
from lab_generate_skill.adapters.map_artifacts.browser_sources import (
    OriginalMapBrowserSources,
)
from lab_generate_skill.adapters.map_artifacts.browser_files import (
    OriginalMapBrowserFiles,
)
from lab_generate_skill.sites.map.browser_collection import MapBrowserCollection


def map_browser_collection(
    configuration: BrowserWorkerConfiguration,
    worker_guard: BrowserStorageGuard,
    clock: Clock,
) -> MapBrowserCollection:
    configuration = BrowserWorkerConfiguration.model_validate(configuration)
    inputs = configuration.map_inputs
    if inputs is None:
        raise ValueError("Fixed Map collection requires its original frozen inputs")
    access = OriginalMapBrowserAccess(
        configuration, "worker", OriginalBrowserAcquisitionReader(), worker_guard
    )
    return MapBrowserCollection(
        configuration.spec,
        inputs,
        OriginalMapBrowserSources(inputs, access),
        OriginalMapBrowserFiles(access),
        OriginalMapCollectionControl(inputs.collection.lifetime_operation, clock),
    )
