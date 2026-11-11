"""Original resource permissions and a once-bound current native task supplier.

Resource admission remains mandatory and independent. Native permission has no
fallback to resource fixtures or another source. No effects, runner or ledger.
"""

import os
import threading
from typing import Literal
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceReady,
    SiteResourceAttempt,
    SiteResourceStarted,
    SiteStepClosed,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_resources import (
    SiteResourceAuthority,
    SiteOriginAuthority,
)
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.ports.site_tasks import SiteTaskAuthority


class TaskSiteAuthority:
    def __init__(
        self,
        spec: SiteResourceSpec,
        acquisition: OperationContext,
        source: SiteResourceAuthority,
        *,
        origin: SiteOriginAuthority | None,
    ) -> None:
        self.spec = SiteResourceSpec.model_validate(spec)
        self.acquisition = OperationContext.model_validate(acquisition)
        self.spec.check_operation(self.acquisition, "execute")
        if source is None:
            raise ValueError("Original resource/source permission is mandatory")
        if (
            isinstance(self.spec.configuration.map_inputs, MapNavigationWorkerInputs)
            and origin is None
        ):
            raise ValueError("Navigation requires explicit original origin authority")
        self.source = source
        self.origin = origin
        self._owner = os.getpid(), threading.get_ident()
        self._ready: SiteResourceReady | None = None
        self._started: SiteInstanceStarted | None = None
        self._native: SiteTaskAuthority | None = None
        self._binding_attempted = self._closing = False

    def _owned(self) -> None:
        if self._owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Native binding changed original owner context")

    def _resource(self, spec: SiteResourceSpec) -> None:
        self._owned()
        if spec != self.spec:
            raise OwnershipConflict("Task site authority changed original resource")

    def bind_native(
        self, authority: SiteTaskAuthority, held: SiteResourceStarted
    ) -> None:
        self._owned()
        if self._binding_attempted or self._closing:
            raise OwnershipConflict("Original native supplier is one-shot")
        self._binding_attempted = True
        held = SiteResourceStarted.model_validate(held)
        if (
            not callable(getattr(authority, "verify_task", None))
            or self._ready is None
            or self._started is None
        ):
            raise OwnershipConflict(
                "Original confirmed site startup and native supplier required"
            )
        if held.ready != self._ready or held.instance != self._started:
            raise OwnershipConflict("Native binding replaced original held site")
        self._native = authority

    def authorize_spawn(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._resource(spec)
        if operation != self.acquisition or self._closing:
            raise OwnershipConflict("Site acquisition changed original operation")
        self.source.authorize_spawn(spec, operation, control)
        if self.origin is not None:
            self.origin.verify_origin(spec, operation, control)

    def verify(
        self,
        configuration: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._owned()
        if configuration != self.spec.configuration or phase not in (
            "configure",
            "start",
            "close",
        ):
            raise OwnershipConflict("Native site changed original configuration")
        if phase == "close":
            self._closing = True
        self.source.verify(configuration, phase, operation, control)

    def verify_ready(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._resource(spec)
        ready = SiteResourceReady.model_validate(ready)
        if self._ready is not None or self._closing:
            raise OwnershipConflict("Original site ready cannot be rebound")
        self.source.verify_ready(spec, ready, operation, control)
        self._ready = SiteResourceReady.model_validate(ready)

    def verify_started(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        started: SiteInstanceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._resource(spec)
        started = SiteInstanceStarted.model_validate(started)
        if self._ready != ready or self._started is not None or self._closing:
            raise OwnershipConflict("Original ready site startup required once")
        self.source.verify_started(spec, ready, started, operation, control)
        self._started = SiteInstanceStarted.model_validate(started)

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        self._owned()
        if (
            configuration != self.spec.configuration
            or self._native is None
            or self._closing
        ):
            raise OwnershipConflict("Original current native supplier is not active")
        request = SiteTaskRequest.model_validate(request)
        control.checkpoint()
        self._native.verify_task(configuration, request, control)
        if self._closing:
            raise OwnershipConflict(
                "Original site began closing during native admission"
            )
        control.checkpoint()

    def verify_closed(
        self,
        spec: SiteResourceSpec,
        attempt: SiteResourceAttempt,
        termination: ProcessTermination | None,
        step: SiteStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self._resource(spec)
        self._closing = True
        return self.source.verify_closed(
            spec, attempt, termination, step, operation, control
        )
