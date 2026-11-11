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
from .ssh_key_environment import SshKeyEnvironmentChecks
from ..reset_identity import (
    original_reset_plan,
    original_closed_attempts,
    original_restore_request,
    original_resume,
    original_task_recovery,
)
from .ssh_key_admission import same_snapshot
from .ssh_key_recovery import SshKeyRestored, SshKeyResumed
from .ssh_key_rules import preserved
from .ssh_key_policy import TASK_RESET_CHECKS, ENVIRONMENT_RESET_CHECKS, HEALTH_CHECKS


class SshKeyStateChecks(SshKeyEnvironmentChecks):
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
        original_reset_plan(plan, env, site, "SSH")
        closures = tuple(
            self.read(ref, "closure-receipt/1", ClosureReceipt, control)
            for ref in selection.closure_refs
        )
        original_closed_attempts(plan, closures, "SSH")
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
        same_snapshot(request, snapshot, env.snapshot_ref)
        original_restore_request(request, result, plan, "SSH")
        restored = SshKeyRestored.model_validate_json(result.private_result)
        if (
            restored.model_dump_json() != result.private_result
            or restored.request != request
            or restored.snapshot != snapshot
        ):
            raise OwnershipConflict(
                "SSH restore changed original complete tree evidence"
            )
        baseline = self.native(snapshot.native_before, snapshot.request, control)
        native_restored = self.native(restored.native, request, control)
        if (
            not preserved(baseline, native_restored)
            or baseline.keys != native_restored.keys
        ):
            raise OwnershipConflict("SSH reset did not restore full native baseline")
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
        original_resume(resume, resumed, intent, request, selection, site, "SSH")
        observed = SshKeyResumed.model_validate_json(resumed.private_result)
        if (
            observed.model_dump_json() != resumed.private_result
            or observed.request != resume
            or observed.restored != restored
        ):
            raise OwnershipConflict("SSH resumed generation lost original restore")
        inspection = request.model_copy(update={"operation": resume.operation})
        native_resumed = self.native(observed.native, inspection, control)
        if (
            not preserved(baseline, native_resumed)
            or baseline.keys != native_resumed.keys
        ):
            raise OwnershipConflict(
                "SSH resumed native state changed original baseline"
            )
        task_recovery = self.read(
            plan.task_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        environment_recovery = self.read(
            plan.environment_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        original_task_recovery(task_recovery, plan, "gitlab-profile-ssh-key", "SSH")
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
                "ORIGINAL_GITLAB_STATE_RESTORED",
            ),
            environment=self.checks(
                ENVIRONMENT_RESET_CHECKS,
                (
                    reference,
                    selection.resume_request_ref,
                    selection.resume_intent_ref,
                    selection.resume_result_ref,
                ),
                "ORIGINAL_GITLAB_SERVICES_RESUMED",
            ),
            health=self.checks(
                HEALTH_CHECKS,
                (reference, selection.resume_result_ref),
                "ORIGINAL_GITLAB_SERVICES_HEALTHY",
            ),
        )
