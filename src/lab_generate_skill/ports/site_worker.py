"""Fixed worker-local instance and mandatory live parent business authority.

Authority must verify original resource intent, release/assets, run and source
before configure; before start it must also verify/persist the original observed
worker resource. Configure itself must not create a site instance. Controller
delegation alone never grants this right.
"""

from typing import Literal, Protocol
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl
from .site_tasks import SiteTasks, SiteTaskAuthority


class WorkerSiteInstance(SiteTasks, Protocol):
    def start(self, control: OperationControl) -> SiteInstanceStarted: ...
    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]: ...


class SiteWorkerAuthority(SiteTaskAuthority, Protocol):
    def verify(
        self,
        configuration: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
