"""Original unchanged -> retire/clear -> new Rails health -> unchanged seam.

Registered task restore authority and browser termination precede begin. It is
split at the existing worker restore/resume boundary, never a second browser
observation. Dirty/unknown state stays isolated; no automatic cold retry here.
"""

import os
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_frontend_lifecycle import (
    MapFrontendStopped,
    MapFrontendCleared,
    MapFrontendResumed,
)
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_services import MapStartupControls
from lab_generate_skill.ports.map_frontend_lifecycle import (
    MapFrontendServices,
    MapFrontendTransients,
)
from lab_generate_skill.ports.native_commands import NativeCommands
from .state_guard import MapStateGuard, MapGuardObservation
from .service_readiness import MapReadiness


class MapFrontendReset:
    def __init__(
        self,
        spec: MapServiceSpec,
        guard: MapStateGuard,
        services: MapFrontendServices,
        files: MapFrontendTransients,
        commands: NativeCommands,
        limits: MapStartupControls,
    ) -> None:
        self.spec = MapServiceSpec.model_validate(spec)
        if (
            guard.spec != self.spec
            or guard.services is not services
            or guard.state != "ready"
        ):
            raise OwnershipConflict(
                "Original installed Map guard/service instance required"
            )
        self.guard, self.services, self.files = guard, services, files
        self.health = MapReadiness(self.spec, commands, services, limits)
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.before: MapGuardObservation | None = None
        self.stopped: MapFrontendStopped | None = None
        self.cleared: MapFrontendCleared | None = None
        self.frontend: NativeNamespaceIdentity | None = None
        self.after: MapGuardObservation | None = None
        self.result: MapFrontendResumed | None = None
        self.error: BaseException | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original Map reset worker/thread required")

    def begin(self, control: OperationControl) -> MapFrontendCleared:
        self._owner()
        if self.state != "new":
            raise InvalidTransition("Original Map restore cannot repeat")
        control.checkpoint()
        self.state = "restoring"
        try:
            self.before = self.guard.require_unchanged(control)
            self.stopped = MapFrontendStopped.model_validate(
                self.services.retire_frontend(control)
            )
            self.cleared = MapFrontendCleared.model_validate(
                self.files.clear(self.spec, self.stopped, control)
            )
            if self.cleared.spec != self.spec or self.cleared.stopped != self.stopped:
                raise OwnershipConflict(
                    "Frontend clearing changed original instance/retirement"
                )
            control.checkpoint()
            self.state = "retired"
            return self.cleared
        except BaseException as error:
            self.error = error
            self.state = "failed"
            raise

    def resume(self, control: OperationControl) -> MapFrontendResumed:
        self._owner()
        if self.state != "retired" or self.cleared is None or self.before is None:
            raise InvalidTransition(
                "Map resume requires original confirmed retirement/clearing"
            )
        control.checkpoint()
        self.state = "resuming"
        try:
            self.services.replace_frontend(control)
            self.health.http(self.spec.ports.web, "/", control, first_rails=True)
            self.frontend = self.services.pin_namespace("rails_server", control)
            self.after = self.guard.require_unchanged(control)
            self.result = MapFrontendResumed(
                cleared=self.cleared,
                before_sha256=self.before.sha256,
                after_sha256=self.after.sha256,
                frontend=self.frontend,
                endpoint=self.spec.endpoint,
            )
            self.services.require_running()
            control.checkpoint()
            self.state = "resumed"
            return self.result
        except BaseException as error:
            self.error = error
            self.state = "failed"
            raise
