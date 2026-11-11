"""Stop held original nginx/PHP payload trees, then observe backend drain.

Original browser closure and sole-task writer admission must already be checked
by parent task authority. Host helpers/whole resource closure remain outside.
"""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from .service_contract import AdminServiceSpec
from .frontend_contract import AdminFrontendStopped
from .backend_drain import AdminDrain


class AdminFrontend:
    def __init__(
        self, spec: AdminServiceSpec, commands: NativeCommands, services: NativeServices
    ) -> None:
        self.spec, self.services = spec, services
        self.drain = AdminDrain(spec, commands)
        self.pins: list[NativeNamespaceIdentity] = []
        self.pinning = False
        self.attempted = False
        self.completed: list[NativeNamespaceStopped] = []
        self.result: AdminFrontendStopped | None = None

    def pin(self, control: OperationControl) -> None:
        if self.pinning:
            raise RuntimeError("Frontend pin already attempted")
        self.pinning = True
        for name in ("nginx", "php"):
            pin = NativeNamespaceIdentity.model_validate(
                self.services.pin_namespace(name, control)
            )
            if pin.service != name:
                raise ValueError("Frontend namespace changed service")
            self.pins.append(pin)

    def stop(self, control: OperationControl) -> AdminFrontendStopped:
        if self.attempted or len(self.pins) != 2:
            raise RuntimeError(
                "Frontend stop requires original two pins and one attempt"
            )
        control.checkpoint()
        self.attempted = True
        try:
            for pin in self.pins:
                stopped = NativeNamespaceStopped.model_validate(
                    self.services.stop_namespace(pin.service, control)
                )
                if stopped.original != pin:
                    raise ValueError("Frontend stop changed original namespace")
                self.completed.append(stopped)
            drained = self.drain.wait(control)
            self.result = AdminFrontendStopped(
                service=self.spec,
                namespaces=(self.completed[0], self.completed[1]),
                backend=drained,
            )
            control.checkpoint()
            return self.result
        except BaseException as error:
            setattr(error, "admin_frontend_completed", tuple(self.completed))
            setattr(error, "admin_frontend_stopped", self.result)
            raise
