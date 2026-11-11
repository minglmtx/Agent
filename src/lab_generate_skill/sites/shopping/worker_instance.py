"""Shopping implementation of the existing fixed worker ports; no new RPC wire."""

from collections.abc import Callable
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from .instance import ShoppingInstance
from .tasks.order_eta_lifecycle import OrderEtaLifecycle
from .tasks.order_eta_resume import OrderEtaResume
from .tasks.navigation_lifecycle import CategoryNavigationLifecycle
from .tasks.navigation_resume import CategoryNavigationResume


class ShoppingWorkerInstance:
    def __init__(
        self, instance: ShoppingInstance, customer: Callable[[OperationControl], str]
    ) -> None:
        self.instance, self.customer = instance, customer
        self.tasks: OrderEtaLifecycle | CategoryNavigationLifecycle | None = None
        self.resumption: OrderEtaResume | CategoryNavigationResume | None = None

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        self.instance.prepare(control)
        endpoint = self.instance.start(control)
        assert self.instance.lease is not None
        return SiteInstanceStarted(
            files=self.instance.files_plan,
            endpoint=endpoint,
            ports=self.instance.lease.ports,
        )

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        if self.tasks is None:
            if self.instance.state != "ready":
                raise RuntimeError("Task requires original ready Shopping worker")
            self.tasks = self._new_task(request)
        return self.tasks.execute_task(request, control=control)

    def _new_task(
        self, request: SiteTaskRequest
    ) -> OrderEtaLifecycle | CategoryNavigationLifecycle:
        identity = request.task
        if (identity.site, identity.contract_version, identity.split) != (
            "shopping",
            1,
            "train",
        ):
            raise ValueError("Unsupported fixed Shopping task identity")
        if identity.family == "recorded_order_eta":
            return OrderEtaLifecycle(self.instance, self.customer)
        if identity.family == "page_navigation":
            return CategoryNavigationLifecycle(self.instance)
        raise ValueError("Unsupported fixed Shopping task family")

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        if self.tasks is None:
            raise RuntimeError("Shopping capture requires original task lifecycle")
        return self.tasks.capture_task(request, control=control)

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        if self.tasks is None or self.resumption is not None:
            raise RuntimeError("Shopping resume requires original task and one call")
        self.resumption = (
            CategoryNavigationResume(self.tasks)
            if isinstance(self.tasks, CategoryNavigationLifecycle)
            else OrderEtaResume(self.tasks)
        )
        return self.resumption.resume_frontend(request, control=control)

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        return self.instance.stop(control)
