"""Fixed native Map assembly; no configuration-selected factories or old runner."""

import os
from lab_generate_skill.domain.map_worker_inputs import MapWorkerInputs
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from pathlib import Path
import socket
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_storage import SiteWorkerGuard
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.site_storage import (
    OriginalMapStateStorage,
)
from lab_generate_skill.adapters.map_artifacts.selection_reader import (
    OriginalMapSelectionReader,
)
from lab_generate_skill.bootstrap.map_database_publisher import (
    MapDatabasePublisher,
)
from lab_generate_skill.sites.map.tasks.reference_dispatch import MapReferenceDispatch
from lab_generate_skill.adapters.map_runtime.stage import NodeMapInputs
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout
from lab_generate_skill.adapters.map_runtime.frontend import NativeMapFrontendFiles
from lab_generate_skill.adapters.map_runtime.frontend_transients import (
    NativeMapFrontendTransients,
)
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.map_runtime.services import OwnedMapServices
from lab_generate_skill.sites.map.instance import MapInstance
from lab_generate_skill.sites.map.state_guard import MapStateGuard
from lab_generate_skill.sites.map.frontend_reset import MapFrontendReset
from lab_generate_skill.sites.map.worker_instance import MapWorkerInstance
from lab_generate_skill.sites.map.tasks.state_lifecycle import MapTaskLifecycle


def build_map_worker(
    configuration: SiteWorkerConfiguration, guard: SiteWorkerGuard
) -> MapWorkerInstance:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    if configuration.site_id != "map" or configuration.map_inputs is None:
        raise ValueError("Explicit original Map worker inputs required")
    access = OriginalMapSiteAccess(
        configuration, "worker", OriginalSiteAcquisitionReader(), guard
    )
    storage = OriginalMapStateStorage(access)
    limits = BoundedMapStartupControls()
    commands = CheckedNativeCommands(ProcessRunner(max_output_bytes=8 * 1024**2))
    sql = CheckedNativeInputCommands(ProcessRunner(max_output_bytes=4 * 1024**2))

    def services(root: str, control: OperationControl) -> NativeServices:
        control.checkpoint()
        return OwnedMapServices(Path(root), limits)

    def tasks(instance: MapInstance, control: OperationControl) -> MapTaskLifecycle:
        spec, group = instance.spec, instance.group
        if spec is None or not isinstance(group, OwnedMapServices):
            raise ValueError(
                "Original prepared Map instance/service ownership required"
            )
        tracker = MapStateGuard(spec, sql, NativeMapPersistentFiles(), group, limits)
        tracker.install(control)
        reset = MapFrontendReset(
            spec, tracker, group, NativeMapFrontendTransients(), commands, limits
        )
        assert configuration.map_inputs is not None
        return MapTaskLifecycle(
            tracker,
            reset,
            storage,
            MapTaskStateCodec(configuration.map_inputs.scope.task),
        )

    def references(task: MapTaskLifecycle) -> MapReferenceDispatch:
        publisher = MapDatabasePublisher(access, task.guard, commands, limits)
        return MapReferenceDispatch(
            task, OriginalMapSelectionReader(access), publisher.publish
        )

    cpus = os.cpu_count()
    if cpus is None:
        raise ValueError("Original host CPU observation unavailable")
    expected_port = (
        configuration.map_inputs.origin.requested_web_port
        if isinstance(configuration.map_inputs, MapNavigationWorkerInputs)
        else None
    )
    instance = MapInstance(
        configuration.map_inputs.runtime,
        files=NodeMapInputs(),
        ports=LoopbackPorts(
            required_prefix=() if expected_port is None else (expected_port,)
        ),
        layout=NativeMapLayout(),
        frontend_files=NativeMapFrontendFiles(),
        commands=commands,
        services=services,
        limits=limits,
        hostname=socket.gethostname(),
        host_cpus=cpus,
        expected_web_port=expected_port,
    )
    return MapWorkerInstance(
        configuration,
        instance,
        storage,
        tasks,
        references if isinstance(configuration.map_inputs, MapWorkerInputs) else None,
    )
