"""Fixed engine/collector dispatch shared by the installed worker and entry checks."""

import os
from lab_generate_skill.sites.map.browser_initialization import (
    MapNativeBrowserInitializer,
)
from lab_generate_skill.sites.map.navigation_browser_initialization import (
    MapNavigationBrowserInitializer,
)
from lab_generate_skill.sites.map.navigation_browser_capture import (
    NavigationBrowserCapture,
)
from lab_generate_skill.sites.map.browser_capture import MapBrowserCapture
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.ports.browser_authority import BrowserAuthority
from lab_generate_skill.ports.browser_storage import BrowserStorageGuard
from lab_generate_skill.ports.lifecycle import Clock
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.bootstrap.browser_capture import browser_collector
from lab_generate_skill.bootstrap.browser_task_files import browser_task_files
from lab_generate_skill.bootstrap.map_browser import map_browser_collection


def build_browser_engine(
    configuration: BrowserWorkerConfiguration,
    authority: BrowserAuthority,
    clock: Clock,
    *,
    worker_guard: BrowserStorageGuard | None,
) -> BrowserGymEngine:
    configuration = BrowserWorkerConfiguration.model_validate(configuration)
    process = None
    collector = browser_collector(configuration)
    if configuration.map_inputs is not None:
        if worker_guard is None:
            raise ValueError(
                "Fixed Map browser requires its original live worker guard"
            )
        process = map_browser_collection(configuration, worker_guard, clock)
        collector = process
    initializer = browser_initializer(
        configuration,
        clock=clock,
        map_evidence=process.files if process is not None else None,
    )
    if isinstance(initializer, MapNavigationBrowserInitializer):
        if process is not None:
            raise ValueError("Navigation cannot attach MapData process collection")
        collector = NavigationBrowserCapture(initializer)
    if isinstance(initializer, MapNativeBrowserInitializer):
        if process is None:
            raise ValueError(
                "Original Map collection required for initial readiness capture"
            )
        collector = MapBrowserCapture(process, initializer)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = configuration.playwright_browsers_path
    os.environ["LD_LIBRARY_PATH"] = ":".join(configuration.library_directories)
    return BrowserGymEngine(
        configuration.spec,
        authority,
        clock,
        initializer,
        collector=collector,
        capture_public_viewport=True,
        task_files=browser_task_files(configuration),
        process_collector=process,
    )
