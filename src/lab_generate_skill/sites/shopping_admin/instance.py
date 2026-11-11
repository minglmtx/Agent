"""Assemble one private Admin worker instance from injected infrastructure.

Requires outer persistent acquisition and supervision. prepare/start are once
only, including uncertain failures; stop retains original facts and never drops
ports or files. External owner must verify quiescence before releasing the held
port lease or removing the predeclared directory. This is NOT SiteProvider or a
ClosureReceipt and does not authorize independent recovery or task execution.
"""

from collections.abc import Callable
from .frontend_contract import AdminFrontendStopped
import os
import threading
from typing import Literal
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.local_ports import LocalPorts, LocalPortLease
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.ports.site_files import SiteFiles
from .instance_contract import AdminInstancePlan
from .service_contract import AdminServiceSpec
from .service_ports import admin_ports
from .service_preflight import preflight_services
from .services import AdminLocalServices
from .frontend_recovery import AdminFrontendRecovery, FrontendRecoveryAuthority
from .frontend_recovery_contract import AdminFrontendRecovered
from .state_contract import AdminStateRestored


class AdminInstance:
    def __init__(
        self,
        plan: AdminInstancePlan,
        *,
        files: SiteFiles,
        ports: LocalPorts,
        commands: NativeCommands,
        services: Callable[[str, OperationControl], NativeServices],
    ) -> None:
        self.plan = AdminInstancePlan.model_validate(plan)
        self._files, self._ports = files, ports
        self.commands, self._services_factory = commands, services
        self._owner = (os.getpid(), threading.get_ident())
        self.port_lease: LocalPortLease | None = None
        self.service_group: NativeServices | None = None
        self.services: AdminLocalServices | None = None
        self.spec: AdminServiceSpec | None = None
        self.stop_facts: tuple[NativeServiceExit, ...] | None = None
        self.frontend_recovery: AdminFrontendRecovery | None = None
        self.state: Literal[
            "new",
            "preparing",
            "prepared",
            "starting",
            "ready",
            "quiescing",
            "quiesced",
            "recovering_frontend",
            "recovered",
            "failed",
            "stopping",
            "stopped",
        ] = "new"

    def _check_owner(self) -> None:
        if self._owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError(
                "Admin instance cannot leave its original process/thread"
            )

    def prepare(self, control: OperationControl) -> AdminServiceSpec:
        self._check_owner()
        if self.state != "new":
            raise RuntimeError(
                "Instance preparation already attempted or instance stopping"
            )
        control.checkpoint()
        self.state = "preparing"
        try:
            # Exact-origin navigation checks the original port before staging
            # large writable assets. Other Admin consumers retain their order.
            if self.plan.navigation_origin is not None:
                self.port_lease = self._ports.reserve(5, control)
                if self.port_lease.ports[0] != self.plan.navigation_origin.web_port:
                    raise ValueError("Navigation lease changed exact original web port")
                self._files.stage(self.plan.files, control)
            else:
                self._files.stage(self.plan.files, control)
                self.port_lease = self._ports.reserve(5, control)
            self.spec = AdminServiceSpec(
                layout=self.plan.layout, ports=admin_ports(self.port_lease)
            )
            self.service_group = self._services_factory(
                self.plan.files.log_root, control
            )
            self.services = AdminLocalServices(
                self.spec,
                self.commands,
                self.service_group,
                navigation_origin=self.plan.navigation_origin,
            )
            preflight_services(self.spec, self.commands, control)
            self.services.prepare(control)
            control.checkpoint()
            self.state = "prepared"
            return self.spec
        except BaseException:
            self.state = "failed"
            raise

    def start(self, control: OperationControl) -> str:
        self._check_owner()
        if self.state != "prepared" or self.services is None:
            raise RuntimeError("Start requires this original prepared instance")
        control.checkpoint()
        self.state = "starting"
        try:
            result = self.services.start(control)
            control.checkpoint()
            self.state = "ready"
            return result
        except BaseException:
            self.state = "failed"
            raise

    def stop_frontend(self, control: OperationControl) -> AdminFrontendStopped:
        self._check_owner()
        if self.state != "ready" or self.services is None:
            raise RuntimeError("Frontend stop requires original ready instance")
        control.checkpoint()
        self.state = "quiescing"
        try:
            result = self.services.frontend.stop(control)
            self.state = "quiesced"
            return result
        except BaseException:
            self.state = "failed"
            raise

    def recover_frontend(
        self,
        restored: AdminStateRestored,
        authority: FrontendRecoveryAuthority,
        control: OperationControl,
    ) -> AdminFrontendRecovered:
        self._check_owner()
        if (
            self.state != "quiesced"
            or self.services is None
            or self.service_group is None
            or self.services.frontend.result is None
            or self.frontend_recovery is not None
            or self.services.frontend.result.service != self.spec
        ):
            raise RuntimeError(
                "Recovery requires original quiesced frontend and one attempt"
            )
        control.checkpoint()
        recovery = AdminFrontendRecovery(
            self.services.frontend.result,
            restored,
            commands=self.commands,
            services=self.service_group,
            authority=authority,
        )
        self.frontend_recovery = recovery
        self.state = "recovering_frontend"
        try:
            result = recovery.recover(control)
            # Health is not permission to repeat the old task lifecycle.
            self.state = "recovered"
            return result
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._check_owner()
        if self.state == "stopped":
            assert self.stop_facts is not None
            return self.stop_facts
        self.state = "stopping"
        try:
            # Do not put a checkpoint before the original group's stop: it must
            # attempt TERM even when cleanup expires, as its own contract states.
            if self.services is not None:
                self.stop_facts = self.services.stop(control)
            elif self.service_group is not None:
                self.stop_facts = self.service_group.stop(control)
            else:
                self.stop_facts = ()
            if any(f.state != "reaped" for f in self.stop_facts):
                raise RuntimeError(
                    "Original Admin service launchers remain unconfirmed"
                )
            self.state = "stopped"
            return self.stop_facts
        except BaseException as error:
            self.state = "failed"
            observed = getattr(error, "service_exits", None)
            if isinstance(observed, tuple) and all(
                isinstance(f, NativeServiceExit) for f in observed
            ):
                self.stop_facts = observed
            setattr(error, "admin_instance_id", self.plan.files.instance_id)
            raise
