"""One declared private store lifecycle over mandatory controlled implementations."""

from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from .storage_admission import OriginalSiteStorageAdmission
from .native_private_evidence import NativePrivateEvidence


class OriginalSitePrivateArtifacts:
    def __init__(
        self,
        plan: SitePrivateEvidencePlan,
        store: ManagedEvidenceStore,
        admission: OriginalSiteStorageAdmission,
    ) -> None:
        self.plan = SitePrivateEvidencePlan.model_validate(plan)
        self.store, self.admission = store, admission
        self.attempted = False
        self.initialized = False
        self.stopped = False
        self.publisher: NativePrivateEvidence | None = None

    def initialize(self, control: OperationControl) -> None:
        if self.attempted or self.stopped:
            raise InvalidTransition("Private site storage initialization is once-only")
        self.attempted = True
        self.store.initialize(control)
        control.checkpoint()
        self.initialized = True

    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None:
        if not self.initialized or self.publisher is not None or self.stopped:
            raise InvalidTransition(
                "Private site facts require initialized store and one original instance"
            )
        context = self.admission.bind_instance(started, control)
        self.publisher = NativePrivateEvidence(
            self.plan, context, self.store, self.admission, profile=self.plan.profile
        )

    def _publisher(self) -> NativePrivateEvidence:
        if self.stopped or self.publisher is None:
            raise InvalidTransition(
                "Original private site store is not bound or stopped"
            )
        return self.publisher

    def publish(
        self, request: SiteTaskRequest, raw: bytes, *, control: OperationControl
    ) -> SitePrivateEvidenceResult:
        return self._publisher().publish(request, raw, control=control)

    def read(
        self,
        request: SiteTaskRequest,
        result: SitePrivateEvidenceResult,
        *,
        control: OperationControl,
    ) -> bytes:
        return self._publisher().read(request, result, control=control)

    def stop_new_io(self) -> None:
        self.stopped = True
        self.admission.stop_new_io()
