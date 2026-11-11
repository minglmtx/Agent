"""Recompute full normal reset from original closures/restore/resume facts."""

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
from .order_eta_environment import OrderEtaEnvironmentChecks
from .order_eta_admission import same_snapshot
from .order_eta_recovery import OrderEtaRestored, OrderEtaResumed
from .order_eta_policy import TASK_RESET_CHECKS, ENVIRONMENT_RESET_CHECKS, HEALTH_CHECKS


class OrderEtaStateChecks(OrderEtaEnvironmentChecks):
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
        codec = self.task_codec(env.scope.task)
        spec, site, snapshot = self._environment(env, control)
        plan = self.read(selection.plan_ref, "reset-plan/1", ResetPlan, control)
        if (plan.scope, plan.spec_ref, plan.environment_recovery_ref) != (
            env.scope,
            env.spec_ref,
            site.token.recovery_ref,
        ):
            raise OwnershipConflict("Shopping reset changed original environment plan")
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
                "Shopping reset needs every original attempt closed"
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
        codec.same_snapshot(request, snapshot, env.snapshot_ref)
        if (
            request.action != "restore"
            or result.request_sha256 != request.digest
            or request.operation.recovery_ref != plan.task_recovery_ref
            or request.operation.parent_operation_id != plan.parent_operation_id
        ):
            raise OwnershipConflict("Shopping reset changed original requested restore")
        restored = codec.restored_type.model_validate_json(result.private_result)
        if (
            restored.model_dump_json() != result.private_result
            or restored.request != request
            or restored.snapshot != snapshot
            or restored.inventory != snapshot.state.inventory
        ):
            raise OwnershipConflict("Shopping restore lost original full state")
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
                "Shopping resume changed original persisted intent/restore"
            )
        observed = codec.resumed_type.model_validate_json(resumed.private_result)
        if (
            observed.model_dump_json() != resumed.private_result
            or observed.request != resume
            or observed.restored != restored
            or observed.protected != snapshot.protected
        ):
            raise OwnershipConflict(
                "Shopping resumed native state differs from original"
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
            codec.recovery_component,
            "1",
            TASK_RESET_CHECKS,
        ):
            raise ValueError("Shopping task recovery omits original full native state")
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
                    *selection.closure_refs,
                ),
                "ORIGINAL_SHOPPING_STATE_RESTORED",
            ),
            environment=self.checks(
                ENVIRONMENT_RESET_CHECKS,
                (
                    reference,
                    selection.resume_request_ref,
                    selection.resume_intent_ref,
                    selection.resume_result_ref,
                ),
                "ORIGINAL_SHOPPING_SERVICES_RESUMED",
            ),
            health=self.checks(
                HEALTH_CHECKS,
                (reference, selection.resume_result_ref),
                "ORIGINAL_SHOPPING_SERVICES_HEALTHY",
            ),
        )
