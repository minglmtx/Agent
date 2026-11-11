"""One deferred original-worker artifact assembly shared by fixed native sites."""

from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.site_storage import SiteWorkerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from .site_private_artifacts import build_site_private_artifacts


class WorkerPrivateArtifacts:
    """Defer storage assembly until start's original control is available."""

    def __init__(
        self, configuration: SiteWorkerConfiguration, guard: SiteWorkerGuard
    ) -> None:
        self.configuration, self.guard = configuration, guard
        self.value: SitePrivateArtifacts | None = None
        self.attempted = False

    def initialize(self, control: OperationControl) -> None:
        if self.attempted:
            raise InvalidTransition("Original site artifact assembly already attempted")
        self.attempted = True
        self.value = build_site_private_artifacts(
            self.configuration, "worker", self.guard, control
        )
        self.value.initialize(control)

    def _value(self) -> SitePrivateArtifacts:
        if self.value is None:
            raise InvalidTransition("Original site artifact assembly not started")
        return self.value

    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None:
        self._value().bind_instance(started, control)

    def publish(
        self, request: SiteTaskRequest, raw: bytes, *, control: OperationControl
    ) -> SitePrivateEvidenceResult:
        return self._value().publish(request, raw, control=control)

    def read(
        self,
        request: SiteTaskRequest,
        result: SitePrivateEvidenceResult,
        *,
        control: OperationControl,
    ) -> bytes:
        return self._value().read(request, result, control=control)

    def stop_new_io(self) -> None:
        if self.value is not None:
            self.value.stop_new_io()
