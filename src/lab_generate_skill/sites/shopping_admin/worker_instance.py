"""Adapt one owned Admin instance to the fixed site-worker lifecycle port.

No independent factory, legacy API, port release or directory deletion. The
worker keeps its lease until process exit; outer domain closure remains required.
"""

import sys
import time
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from .instance import AdminInstance
from .tasks.product_lifecycle import AdminProductLifecycle
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from .tasks.product_resume import ProductResume
from .tasks.navigation_lifecycle import AdminNavigationLifecycle
from .tasks.navigation_resume import NavigationResume


class AdminWorkerInstance:
    def __init__(self, instance: AdminInstance) -> None:
        self.instance = instance
        self.tasks: AdminProductLifecycle | AdminNavigationLifecycle | None = None
        self.resumption: ProductResume | NavigationResume | None = None

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        self._progress("prepare_begin")
        self.instance.prepare(control)
        self._progress("prepare_complete")
        endpoint = self.instance.start(control)
        self._progress("start_complete")
        assert self.instance.port_lease is not None
        return SiteInstanceStarted(
            files=self.instance.plan.files,
            endpoint=endpoint,
            ports=self.instance.port_lease.ports,
        )

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        if self.instance.state != "ready" or self.instance.spec is None:
            raise RuntimeError("Task requires original ready Admin instance")
        if self.tasks is None:
            family = (
                request.task.site,
                request.task.family,
                request.task.contract_version,
            )
            if family == ("shopping_admin", "page_navigation", 1):
                self.tasks = AdminNavigationLifecycle(
                    self.instance.spec,
                    self.instance.commands,
                    self.instance.stop_frontend,
                )
            elif family == ("shopping_admin", "product_description", 1):
                self.tasks = AdminProductLifecycle(
                    self.instance.spec,
                    self.instance.commands,
                    self.instance.stop_frontend,
                )
            else:
                raise ValueError("Unsupported fixed Admin task family")
        # Retain the explicit union after both construction branches; no
        # untyped or unsupported local task provider can enter dispatch.
        assert isinstance(self.tasks, (AdminProductLifecycle, AdminNavigationLifecycle))
        return self.tasks.execute_task(request, control=control)

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        if self.instance.state != "ready" or self.tasks is None:
            raise RuntimeError("Capture requires original prepared Admin task")
        if isinstance(self.tasks, AdminNavigationLifecycle):
            return self.tasks.capture_task(request, control=control)
        return self.tasks.capture_task(request, control=control)

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        if self.tasks is None or self.resumption is not None:
            raise RuntimeError("Resume requires original task lifecycle and one call")
        self.resumption = (
            NavigationResume(self.instance, self.tasks)
            if isinstance(self.tasks, AdminNavigationLifecycle)
            else ProductResume(self.instance, self.tasks)
        )
        return self.resumption.resume_frontend(request, control=control)

    @staticmethod
    def _progress(phase: str) -> None:
        # Callers below supply fixed lifecycle labels only, never task/config data.
        try:
            sys.stderr.write(f"SITE_INSTANCE_PHASE {phase} {time.monotonic():.6f}\n")
            sys.stderr.flush()
        except OSError:
            # Diagnostics are best effort; a broken controller pipe must not skip
            # the original instance's independent cleanup.
            pass

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._progress("stop_begin")
        result = self.instance.stop(control)
        self._progress("stop_complete")
        return result
