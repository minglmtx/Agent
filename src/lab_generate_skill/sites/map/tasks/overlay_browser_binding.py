"""Selected explicit Map browser joins complete original site preparation files."""

import hashlib
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from .navigation_admission import task_input as navigation_input
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import MapStateReads


class OverlayBrowserChecks(MapStateReads):
    def check(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        request: SiteTaskRequest,
        initialization: BrowserInitialization,
        control: OperationControl,
    ) -> None:
        if not isinstance(
            initialization, (MapNativeInitialization, MapNavigationInitialization)
        ):
            raise OwnershipConflict("Explicit selected Map initialization required")
        self.check_prepared(
            publication.selection.result_ref,
            request,
            initialization,
            site_spec.configuration,
            site.instance,
            control,
        )

    def check_prepared(
        self,
        result_ref: EvidenceRef,
        request: SiteTaskRequest,
        selected: MapNativeInitialization | MapNavigationInitialization,
        configuration: SiteWorkerConfiguration,
        instance: SiteInstanceStarted,
        control: OperationControl,
    ) -> None:
        configuration = SiteWorkerConfiguration.model_validate(configuration)
        instance = SiteInstanceStarted.model_validate(instance)
        if isinstance(selected, MapNavigationInitialization):
            selected = MapNavigationInitialization.model_validate(selected)
        else:
            selected = MapNativeInitialization.model_validate(selected)
        request = SiteTaskRequest.model_validate(request)
        request.check_site(configuration)
        inputs = configuration.map_inputs
        if (
            configuration.site_id != "map"
            or inputs is None
            or instance.files != configuration.files
            or (
                selected.endpoint != instance.endpoint
                or len(instance.ports) != 6
                or inputs.private_input_sha256
                != hashlib.sha256(request.private_input.encode()).hexdigest()
            )
        ):
            raise OwnershipConflict(
                "Map browser changed original configured instance/source"
            )
        if isinstance(selected, MapNavigationInitialization):
            private = navigation_input(request)
            if (
                not isinstance(inputs, MapNavigationWorkerInputs)
                or private.native_contract_ref.sha256 != selected.native_contract_sha256
                or inputs.native_contract_sha256 != selected.native_contract_sha256
            ):
                raise OwnershipConflict(
                    "Navigation browser changed original task contract"
                )
        elif request.task.family != "native_route_map_data":
            raise OwnershipConflict(
                "Navigation cannot masquerade as MapData initialization"
            )
        result = self.read(result_ref, "site-task-result/1", SiteTaskResult, control)
        observed = self.prepared(result, request, control)
        for native in (observed.snapshot.native, observed.native):
            if (
                native.plan.token != configuration.token
                or native.plan.scope != inputs.scope
                or native.plan.workspace_root != configuration.files.workspace_root
            ):
                raise OwnershipConflict(
                    "Map browser changed original full-state allocation/scope"
                )
        control.checkpoint()
