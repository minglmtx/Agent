"""Original acquired Map participant and frozen source-bound full-file permissions.

Outer task authority remains mandatory. This capability admits only storage for
the original configured task/attempt and exact input; it cannot execute a task.
"""

import os
import threading
from typing import Literal
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.map_private_artifact import (
    MapArtifactPlan,
    parse_map_artifact_plan,
)
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_storage import SiteAcquisitionReader, SiteWorkerGuard
from lab_generate_skill.adapters.sites.storage_participant import observe_original
from .site_plan import original_site_plan


class OriginalMapSiteAccess:
    def __init__(
        self,
        configuration: SiteWorkerConfiguration,
        participant: Literal["worker", "controller"],
        original: SiteAcquisitionReader,
        worker_guard: SiteWorkerGuard | None,
        started: SiteInstanceStarted | None = None,
    ) -> None:
        self.configuration = SiteWorkerConfiguration.model_validate(configuration)
        if self.configuration.site_id != "map" or self.configuration.map_inputs is None:
            raise OwnershipConflict("Original fixed Map configuration required")
        if participant not in ("worker", "controller") or (participant == "worker") != (
            worker_guard is not None
        ):
            raise ValueError("Only original Map worker requires its live owner guard")
        self.inputs = self.configuration.map_inputs
        self.participant, self.original, self.worker_guard = (
            participant,
            original,
            worker_guard,
        )
        self.owner = os.getpid(), threading.get_ident()
        self.started = (
            SiteInstanceStarted.model_validate(started) if started is not None else None
        )
        if self.started is not None:
            self._instance(self.started)
        self.requests: dict[str, SiteTaskRequest] = {}
        self.stopped = False

    def _instance(self, started: SiteInstanceStarted) -> None:
        if started.files != self.configuration.files or len(started.ports) != 6:
            raise OwnershipConflict(
                "Map file permission changed original instance/ports"
            )

    def observe(self, control: OperationControl) -> None:
        if self.stopped:
            raise InvalidTransition("Original Map file capability is stopped")
        observe_original(
            self.configuration,
            self.participant,
            self.original,
            self.worker_guard,
            self.owner,
            control,
        )
        if self.stopped:
            raise InvalidTransition(
                "Original Map capability stopped during observation"
            )

    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None:
        if self.started is not None:
            raise InvalidTransition(
                "Map file capability already bound to original instance"
            )
        self.observe(control)
        started = SiteInstanceStarted.model_validate(started)
        self._instance(started)
        self.started = started

    def stop_new_io(self) -> None:
        self.stopped = True

    def plan(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> MapArtifactPlan:
        request = SiteTaskRequest.model_validate(request)
        declared = self._plan(request)
        op = request.operation
        self.observe(control)
        if self.started is None:
            raise InvalidTransition(
                "Map artifacts require original bound started instance"
            )
        prior = self.requests.get(op.operation_id)
        if prior is not None and prior != request:
            raise OwnershipConflict(
                "Map artifact operation ID changed original request"
            )
        self.requests[op.operation_id] = request
        return declared

    def _plan(self, request: SiteTaskRequest) -> MapArtifactPlan:
        return original_site_plan(self.configuration, request)

    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        plan = parse_map_artifact_plan(plan)
        if phase not in ("initialize", "write", "seal", "read") or (
            self.participant != "worker" and phase != "read"
        ):
            raise OwnershipConflict("Only original worker may publish Map native files")
        if self.started is None or not any(
            self._plan(r) == plan for r in self.requests.values()
        ):
            raise OwnershipConflict(
                "Map file plan is not bound to its original request"
            )
        self.observe(control)
