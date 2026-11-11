"""Private site artifacts require original durable ownership and live kernel scope.

This resource-bound capability grants storage only. Parent task authority remains
mandatory; no RunPlan/source claim or permission is invented from a declaration.
Original worker and controller roles are fixed by trusted bootstrap.
"""

import hashlib
import os
import threading
from typing import Literal
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_storage_original import SiteStorageOriginal
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    check_evidence_cleanup,
)
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.storage_scope import check_private_storage_operation
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.site_storage import SiteAcquisitionReader, SiteWorkerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from .storage_participant import observe_original


class OriginalSiteStorageAdmission:
    def __init__(
        self,
        configuration: SiteWorkerConfiguration,
        participant: Literal["worker", "controller"],
        original: SiteAcquisitionReader,
        worker_guard: SiteWorkerGuard | None,
        started: SiteInstanceStarted | None,
    ) -> None:
        self.configuration = SiteWorkerConfiguration.model_validate(configuration)
        if (
            self.configuration.site_id not in ("gitlab", "reddit")
            or self.configuration.private_evidence is None
        ):
            raise OwnershipConflict(
                "Private site store must be declared before original acquisition"
            )
        if participant not in ("worker", "controller") or (participant == "worker") != (
            worker_guard is not None
        ):
            raise ValueError(
                "Only original worker requires its live parent/supervisor guard"
            )
        self.plan = self.configuration.private_evidence
        self.profile = self.plan.profile
        self.participant, self.original, self.worker_guard = (
            participant,
            original,
            worker_guard,
        )
        self.owner = (os.getpid(), threading.get_ident())
        self.accepted: dict[str, OperationContext] = {}
        self.stopped = False
        self.started = (
            SiteInstanceStarted.model_validate(started) if started is not None else None
        )
        if self.started is not None and self.started.files != self.configuration.files:
            raise OwnershipConflict("Storage instance changed original allocated files")

    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> SitePrivateEvidenceContext:
        if self.started is not None or self.stopped:
            raise InvalidTransition(
                "Original storage site instance already bound or stopped"
            )
        original = self._original(control)
        started = SiteInstanceStarted.model_validate(started)
        if started.files != self.configuration.files:
            raise OwnershipConflict("Storage instance changed original allocated files")
        self.started = started
        return SitePrivateEvidenceContext(
            site_id=self.profile.site_id,
            configuration_sha256=hashlib.sha256(
                self.configuration.model_dump_json().encode()
            ).hexdigest(),
            token=self.configuration.token,
            instance=started,
            owner_guard=original.acquired.details.ready.worker.owner_guard,
        )

    def stop_new_io(self) -> None:
        self.stopped = True

    def _original(
        self, control: OperationControl, *, cleanup: bool = False
    ) -> SiteStorageOriginal:
        return observe_original(
            self.configuration,
            self.participant,
            self.original,
            self.worker_guard,
            self.owner,
            control,
            cleanup=cleanup,
        )

    def _binding(
        self, binding: EvidenceSessionBinding, config: EvidenceStorageConfig
    ) -> None:
        if binding != self.plan.binding or config != self.plan.config:
            raise OwnershipConflict(
                "Private site store changed its declared binding/configuration"
            )

    def authorize_storage(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._binding(binding, config)
        operation = check_private_storage_operation(
            self.configuration.token.owner, operation
        )
        if self.stopped or operation.operation_id in self.accepted:
            raise InvalidTransition(
                "Private site storage stopped or operation already admitted"
            )
        self._original(control)
        if self.stopped:
            raise InvalidTransition("Private site storage stopped during admission")
        self.accepted[operation.operation_id] = operation

    def authorize_cleanup(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        original: OperationContext,
        cleanup: OperationContext,
        ending: StorageProcessEnd | None,
        control: OperationControl,
    ) -> None:
        self._binding(binding, config)
        original = check_private_storage_operation(
            self.configuration.token.owner, original
        )
        cleanup = OperationContext.model_validate(cleanup)
        check_evidence_cleanup(original, cleanup)
        if (
            cleanup.cancellation_ref is not None
            or self.accepted.get(original.operation_id) != original
        ):
            raise OwnershipConflict(
                "Private cleanup requires exact previously admitted operation"
            )
        observed = self._original(control, cleanup=True)
        expected = observed.acquired.details.ready.worker.owner_guard
        controller = (
            expected.worker if self.participant == "worker" else expected.controller
        )
        if ending is not None:
            ending = StorageProcessEnd.model_validate(ending)
            if ending.controller != controller:
                raise OwnershipConflict(
                    "Private cleanup ending belongs to another controller"
                )

    def authorize(
        self,
        plan: SitePrivateEvidencePlan,
        context: SitePrivateEvidenceContext,
        request: SiteTaskRequest,
        phase: Literal["publish", "read"],
        control: OperationControl,
    ) -> None:
        if phase not in ("publish", "read") or plan != self.plan or self.stopped:
            raise OwnershipConflict(
                "Private native fact changed original site storage scope"
            )
        if phase == "publish" and self.participant != "worker":
            raise OwnershipConflict(
                "Only original native worker publishes authoritative native facts"
            )
        observed = self._original(control)
        guard = observed.acquired.details.ready.worker.owner_guard
        if (
            context.site_id != self.profile.site_id
            or context.configuration_sha256
            != hashlib.sha256(self.configuration.model_dump_json().encode()).hexdigest()
            or context.owner_guard != guard
            or context.token != self.configuration.token
            or self.started is None
            or context.instance != self.started
        ):
            raise OwnershipConflict(
                "Native fact lost original site configuration/guard"
            )
        request = SiteTaskRequest.model_validate(request)
        request.check_site(self.configuration)
        if (
            request.task.site,
            request.task.family,
            request.task.contract_version,
            request.task.split,
        ) != (self.profile.site_id, self.profile.family, 1, "train"):
            raise OwnershipConflict("Unsupported private native fact consumer")
        control.checkpoint()
