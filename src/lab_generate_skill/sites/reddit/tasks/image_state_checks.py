"""Recompute full reset/native baseline and original restored generation health."""

import hashlib
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.lifecycle import ClosureReceipt, RecoveryPlan
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .image_environment import ImageEnvironmentChecks
from .image_recovery import ImageRestored, ImageResumed
from .image_policy import TASK_RESET_CHECKS, ENVIRONMENT_RESET_CHECKS, HEALTH_CHECKS


class ImageStateChecks(ImageEnvironmentChecks):
    def reset(
        self,
        selection: ResetSelection,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> QualifiedResetChecks:
        selection = ResetSelection.model_validate(selection)
        env = self.read(
            selection.environment_selection_ref,
            "environment-selection/1",
            EnvironmentSelection,
            control,
        )
        spec, site, snapshot = self._environment(env, control)
        plan = self.read(selection.plan_ref, "reset-plan/1", ResetPlan, control)
        if (plan.scope, plan.spec_ref, plan.environment_recovery_ref) != (
            env.scope,
            env.spec_ref,
            site.token.recovery_ref,
        ):
            raise OwnershipConflict("Reddit reset changed original environment plan")
        closures = tuple(
            self.read(ref, "closure-receipt/1", ClosureReceipt, control)
            for ref in selection.closure_refs
        )
        if (
            sum(t.resource_kind == "browser" for t in plan.attempt_allocations) != 1
            or tuple(c.token for c in closures) != plan.attempt_allocations
            or any(c.status != "closed" for c in closures)
        ):
            raise OwnershipConflict(
                "Reddit reset requires every original attempt resource closed"
            )
        request = self.read(
            selection.restore_request_ref,
            "site-task-request/2",
            SiteTaskRequest,
            control,
        )
        result = self.read(
            selection.restore_result_ref, "site-task-result/1", SiteTaskResult, control
        )
        request.check_site(site.configuration)
        snapshot.check_request(request)
        if request.snapshot_ref != env.snapshot_ref:
            raise OwnershipConflict(
                "Reddit restore changed original persisted snapshot"
            )
        if (
            request.action != "restore"
            or result.request_sha256 != request.digest
            or request.operation.recovery_ref != plan.task_recovery_ref
            or request.operation.parent_operation_id != plan.parent_operation_id
        ):
            raise OwnershipConflict("Reddit reset changed original restore request")
        restored = ImageRestored.model_validate_json(result.private_result)
        if (
            restored.model_dump_json() != result.private_result
            or restored.request != request
            or restored.snapshot != snapshot
        ):
            raise OwnershipConflict(
                "Reddit restore changed original complete tree evidence"
            )
        baseline = self.reference(snapshot.native_before, snapshot.request, control)
        resume = self.read(
            selection.resume_request_ref,
            "site-resume-request/1",
            SiteResumeRequest,
            control,
        )
        resumed = self.read(
            selection.resume_result_ref,
            "site-resume-result/1",
            SiteResumeResult,
            control,
        )
        intent = self.read(
            selection.resume_intent_ref,
            "site-resume-intent/1",
            SiteResumeIntent,
            control,
        )
        resume.check_site(site.configuration)
        if (
            resume.restore_request,
            resume.restore_result_ref,
            resumed.request_sha256,
            intent.request,
            intent.configuration_sha256,
        ) != (
            request,
            selection.restore_result_ref,
            resume.digest,
            resume,
            hashlib.sha256(site.configuration.model_dump_json().encode()).hexdigest(),
        ):
            raise OwnershipConflict(
                "Reddit resume changed original persisted restore/intent"
            )
        observed = ImageResumed.model_validate_json(resumed.private_result)
        if (
            observed.model_dump_json() != resumed.private_result
            or observed.request != resume
            or observed.restored != restored
        ):
            raise OwnershipConflict("Reddit resumed generation lost original restore")
        inspection = request.model_copy(update={"operation": resume.operation})
        native_resumed = self.capture(observed.native, inspection, control)
        if baseline.capture != native_resumed:
            raise OwnershipConflict(
                "Reddit resumed native state changed original baseline"
            )
        task_recovery = self.read(
            plan.task_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        environment_recovery = self.read(
            plan.environment_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        if (
            task_recovery.owner,
            task_recovery.attempt_id,
            task_recovery.baseline_ref,
            task_recovery.restore_component_id,
            task_recovery.restore_component_version,
            task_recovery.state_coverage,
        ) != (
            plan.scope.owner,
            plan.scope.attempt_id,
            plan.spec_ref,
            "reddit-native-image",
            "1",
            TASK_RESET_CHECKS,
        ):
            raise ValueError("Reddit task recovery omits original full state")
        return QualifiedResetChecks(
            allocation_id=site.token.allocation_id,
            plan=plan,
            spec=spec,
            task_recovery=task_recovery,
            environment_recovery=environment_recovery,
            closures=closures,
            task=self.checks(
                TASK_RESET_CHECKS,
                (
                    reference,
                    env.snapshot_ref,
                    selection.restore_request_ref,
                    selection.restore_result_ref,
                    selection.resume_result_ref,
                    observed.native.payload_ref,
                    *selection.closure_refs,
                ),
                "ORIGINAL_REDDIT_STATE_RESTORED",
            ),
            environment=self.checks(
                ENVIRONMENT_RESET_CHECKS,
                (
                    reference,
                    selection.resume_request_ref,
                    selection.resume_intent_ref,
                    selection.resume_result_ref,
                ),
                "ORIGINAL_REDDIT_SERVICES_RESUMED",
            ),
            health=self.checks(
                HEALTH_CHECKS,
                (reference, selection.resume_result_ref),
                "ORIGINAL_REDDIT_SERVICES_HEALTHY",
            ),
        )
