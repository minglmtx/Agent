"""Pure original GitLab restore/closure/intent identity; no effects or reads."""

import hashlib
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.lifecycle import ClosureReceipt, RecoveryPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from .state_policy import TASK_RESET_CHECKS


def original_reset_plan(
    plan: ResetPlan, env: EnvironmentSelection, site: SiteResourceSpec, label: str
) -> None:
    if (plan.scope, plan.spec_ref, plan.environment_recovery_ref) != (
        env.scope,
        env.spec_ref,
        site.token.recovery_ref,
    ):
        raise OwnershipConflict(label + " reset changed original environment plan")


def original_closed_attempts(
    plan: ResetPlan, closures: tuple[ClosureReceipt, ...], label: str
) -> None:
    if (
        sum(t.resource_kind == "browser" for t in plan.attempt_allocations) != 1
        or tuple(c.token for c in closures) != plan.attempt_allocations
        or any(c.status != "closed" for c in closures)
    ):
        raise OwnershipConflict(
            label + " reset requires every original attempt resource closed"
        )


def original_restore_request(
    request: SiteTaskRequest, result: SiteTaskResult, plan: ResetPlan, label: str
) -> None:
    if (
        request.action != "restore"
        or result.request_sha256 != request.digest
        or request.operation.recovery_ref != plan.task_recovery_ref
        or request.operation.parent_operation_id != plan.parent_operation_id
    ):
        raise OwnershipConflict(label + " reset changed original restore request")


def original_resume(
    resume: SiteResumeRequest,
    resumed: SiteResumeResult,
    intent: SiteResumeIntent,
    request: SiteTaskRequest,
    selection: ResetSelection,
    site: SiteResourceSpec,
    label: str,
) -> None:
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
            label + " resume changed original persisted restore/intent"
        )


def original_task_recovery(
    task_recovery: RecoveryPlan, plan: ResetPlan, component: str, label: str
) -> None:
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
        component,
        "1",
        TASK_RESET_CHECKS,
    ):
        raise ValueError(label + " task recovery omits original full state")
