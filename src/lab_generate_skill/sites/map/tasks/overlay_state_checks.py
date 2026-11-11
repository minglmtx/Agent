"""Original browser closure and unchanged-state Rails reset/resume qualification."""

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
from .overlay_environment import OverlayEnvironmentChecks
from .state_admission import snapshot_reference
from .state_codec import MapTaskStateCodec


class OverlayStateChecks(OverlayEnvironmentChecks):
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
        facts = self._environment(env, control)
        site, snapshot, spec = facts.site, facts.snapshot, facts.spec
        codec = MapTaskStateCodec(env.scope.task)
        plan = self.read(selection.plan_ref, "reset-plan/1", ResetPlan, control)
        if (plan.scope, plan.spec_ref, plan.environment_recovery_ref) != (
            env.scope,
            env.spec_ref,
            site.token.recovery_ref,
        ):
            raise OwnershipConflict("Map reset changed original environment plan")
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
                "Map reset requires every original attempt resource closed"
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
        snapshot_reference(
            request,
            snapshot.request,
            snapshot.model_dump_json().encode(),
            env.snapshot_ref,
            schema_version=codec.snapshot_schema,
        )
        if (
            request.action != "restore"
            or result.request_sha256 != request.digest
            or request.operation.recovery_ref != plan.task_recovery_ref
            or request.operation.parent_operation_id != plan.parent_operation_id
        ):
            raise OwnershipConflict("Map reset changed original restore parent/request")
        restored = codec.restored_type.model_validate_json(result.private_result)
        if (
            restored.model_dump_json() != result.private_result
            or restored.request != request
            or restored.snapshot != snapshot
            or restored.cleared.spec != facts.service
        ):
            raise OwnershipConflict(
                "Map restore changed original state/instance/retirement"
            )
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
                "Map resume changed original persisted restore/intent"
            )
        observed = codec.resumed_type.model_validate_json(resumed.private_result)
        if (
            observed.model_dump_json() != resumed.private_result
            or observed.request != resume
            or observed.restored != restored
        ):
            raise OwnershipConflict("Map resumed generation lost original restore")
        if (
            resume.operation.recovery_ref != plan.environment_recovery_ref
            or resume.operation.parent_operation_id != request.operation.operation_id
        ):
            raise OwnershipConflict(
                "Map resume changed original recovery/restore parent"
            )
        before = self.native(snapshot.native, snapshot.request, control)
        inspection = SiteTaskRequest.model_validate(
            request.model_copy(update={"operation": resume.operation})
        )
        after = self.native(observed.native, inspection, control)
        reset = observed.resumed
        if (
            before.sha256 != after.sha256
            or reset.before_sha256 != before.sha256
            or reset.after_sha256 != after.sha256
            or reset.endpoint != facts.started.instance.endpoint
        ):
            raise OwnershipConflict(
                "Map reset did not preserve complete original persistent state"
            )
        old = restored.cleared.stopped
        worker = facts.started.ready.worker.owner_guard.worker
        if old.generation != 1:
            raise OwnershipConflict(
                "Selected Map reset lost its original first Rails generation"
            )
        for namespace in (old.namespace.original, reset.frontend):
            for process in (namespace.launcher, namespace.init):
                if (process.node_id, process.boot_id) != (
                    worker.node_id,
                    worker.boot_id,
                ) or process.start_ticks < worker.start_ticks:
                    raise OwnershipConflict(
                        "Map reset namespace changed original worker host/boot/order"
                    )
        if (
            reset.frontend.launcher.start_ticks
            < old.namespace.original.launcher.start_ticks
            or reset.frontend.init.start_ticks < old.namespace.original.init.start_ticks
        ):
            raise OwnershipConflict("Map resumed namespace predates original frontend")
        task_recovery = self.read(
            plan.task_recovery_ref, "recovery-plan/1", RecoveryPlan, control
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
            spec.task_reset_checks,
        ):
            raise OwnershipConflict("Map task recovery changed original complete scope")
        return QualifiedResetChecks(
            allocation_id=site.token.allocation_id,
            plan=plan,
            spec=spec,
            task_recovery=task_recovery,
            environment_recovery=facts.recovery,
            closures=closures,
            task=self.checks(
                spec.task_reset_checks,
                (
                    reference,
                    env.snapshot_ref,
                    selection.restore_request_ref,
                    selection.restore_result_ref,
                    *selection.closure_refs,
                ),
                "ORIGINAL_MAP_STATE_UNCHANGED_FRONTEND_RETIRED",
            ),
            environment=self.checks(
                spec.environment_reset_checks,
                (
                    reference,
                    selection.resume_request_ref,
                    selection.resume_intent_ref,
                    selection.resume_result_ref,
                ),
                "ORIGINAL_MAP_FRONTEND_RESUMED",
            ),
            health=self.checks(
                spec.health_checks,
                (reference, env.snapshot_ref, selection.resume_result_ref),
                "ORIGINAL_MAP_SERVICES_HEALTHY",
            ),
        )
