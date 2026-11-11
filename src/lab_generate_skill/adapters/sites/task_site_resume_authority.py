"""Current original finalizer supplies resume rights on the existing fixed port.

Native restore, closed browser and original source/exclusive cleanup authority
remain mandatory. No inferred source grant, request ledger or repeat permission.
"""

import hashlib
import os
import threading
from collections.abc import Callable
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_finalization import RecordedTaskFinalization
from .task_held_site import original_acquired_task_site


class OriginalTaskSiteResumeAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        finalization: Callable[[], RecordedTaskFinalization],
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        if not callable(finalization):
            raise ValueError("Original finalizer supplier required")
        self.finalization = finalization
        self.owner = os.getpid(), threading.get_ident()
        self.consumed = False

    def verify_resume(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Resume authority changed original owner")
        if self.consumed:
            raise DispatchAlreadyCommitted(
                "Original resume permission already consumed"
            )
        request = SiteResumeRequest.model_validate(request)
        f = self.finalization()
        s, p = f.state, f.preparation
        if (
            f.plan != self.plan
            or configuration != p.spec.configuration
            or s.phase != "resuming"
            or not s.restore_attempted
            or s.closed is None
            or s.restore_request is None
            or s.restore_request_ref is None
            or s.restore_result is None
            or s.restore_result_ref is None
            or s.resume_request_ref is None
            or s.resume_request != request
            or request.restore_request != s.restore_request
            or request.restore_result_ref != s.restore_result_ref
            or request.operation.operation_id != f.declaration.resume_operation_id
            or request.operation.recovery_ref != f.reset.environment_recovery_ref
            or s.closed.reset_plan != f.reset
            or not s.closed.closures
            or any(c.status != "closed" for c in s.closed.closures)
        ):
            raise OwnershipConflict(
                "Only original confirmed restore/closure may resume"
            )
        request.check_site(configuration)
        if (
            f.reads.parse(
                s.resume_request_ref,
                "site-resume-request/1",
                SiteResumeRequest,
                control,
            )
            != request
            or f.reads.parse(
                s.restore_request_ref, "site-task-request/2", SiteTaskRequest, control
            )
            != s.restore_request
            or f.reads.parse(
                s.restore_result_ref, "site-task-result/1", SiteTaskResult, control
            )
            != s.restore_result
            or s.restore_result.request_sha256 != s.restore_request.digest
        ):
            raise OwnershipConflict("Resume changed original persisted restore lineage")
        if (
            intent_ref.content_schema,
            intent_ref.visibility,
            intent_ref.media_type,
            intent_ref.producer,
        ) != ("site-resume-intent/1", "private", "application/json", "site-resume-v1"):
            raise OwnershipConflict("Original resume intent producer required")
        intent = f.reads.parse(
            intent_ref, "site-resume-intent/1", SiteResumeIntent, control
        )
        if (
            intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict("Resume differs from original fixed worker intent")
        for closure, ref in zip(s.closed.closures, s.closed.closure_refs, strict=True):
            if (
                f.evidence.read(ref, control=control)
                != closure.model_dump_json().encode()
            ):
                raise OwnershipConflict("Original browser closure bytes changed")
        f.authority.verify(
            self.plan,
            f.declaration,
            tuple(
                dict.fromkeys(
                    (*p.state.references, *s.references, *f.browser.references)
                )
            ),
            request.operation,
            control,
        )
        original_acquired_task_site(p, request.operation, control)
        control.checkpoint()
        self.consumed = True
