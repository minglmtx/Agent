"""Private task execution, never arbitrary script dispatch or model observation."""

from typing import Protocol
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from .lifecycle import OperationControl


class SiteTasks(Protocol):
    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult: ...


class SiteTaskAuthority(Protocol):
    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        """Verify actual binding/input sources, original recovery and durable once intent.

        Prepare requires no competing writer and committed task recovery before
        any effect. Inspect is read-only, not permission to repeat prepare.
        """
        ...


class SiteTaskInputChecks(Protocol):
    """Site-specific complete private/recovery/snapshot rules, without I/O.

    These checks do not grant current source permission or native dispatch.
    """

    def verify_inputs(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        binding: TaskBinding,
        recovery: RecoveryPlan,
        environment: RecoveryPlan,
        snapshot_bytes: bytes | None,
        snapshot_request: SiteTaskRequest | None,
        control: OperationControl,
    ) -> None: ...
