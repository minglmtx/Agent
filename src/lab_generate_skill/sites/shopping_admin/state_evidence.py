"""Recompute selected Admin state facts from original bytes, with no native calls.

Physical provenance, ordering and live permissions remain mandatory authority
checks. A complete descriptor never establishes who produced it or when.
"""

import hashlib
from typing import TypeVar
from abc import ABC, abstractmethod
from dataclasses import dataclass
from lab_generate_skill.domain.identity import TaskIdentity
from .state_contract import AdminStateSnapshot, AdminStateRestored
from .frontend_contract import AdminFrontendStopped
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    ClosureReceipt,
)
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_contract import ARTIFACT_PATHS
from .instance_contract import AdminInstancePlan
from .frontend_recovery_contract import AdminFrontendRecovered

T = TypeVar("T", bound=Contract)


ENVIRONMENT_CHECKS = (
    "admin.instance.original",
    "admin.services.initial_ready",
    "admin.snapshot.complete",
)
ENVIRONMENT_RESET_CHECKS = ("admin.frontend.resumed",)
HEALTH_CHECKS = ("admin.backends.ready", "admin.frontend.ready")


@dataclass(frozen=True)
class AdminRecoveryView:
    request: SiteTaskRequest
    state: AdminStateSnapshot
    task_state: Contract | None


@dataclass(frozen=True)
class AdminRestoredView:
    task: TaskIdentity
    operation: OperationContext
    snapshot_ref: EvidenceRef
    state: AdminStateRestored
    frontend: AdminFrontendStopped
    task_state: Contract | None


class AdminStateChecks(ABC):
    task_reset_checks: tuple[str, ...]
    restore_component: tuple[str, str]

    @abstractmethod
    def specification(self, task: TaskIdentity) -> InitialStateSpec: ...

    @abstractmethod
    def snapshot(
        self, reference: EvidenceRef, control: OperationControl
    ) -> AdminRecoveryView: ...

    @abstractmethod
    def restored(self, raw: str) -> AdminRestoredView: ...
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def read(
        self, ref: EvidenceRef, schema: str, model: type[T], control: OperationControl
    ) -> T:
        private_state_ref(ref, schema)
        if ref.media_type != "application/json":
            raise ValueError("State qualification requires private JSON")
        raw = self.store.read(ref, control=control)
        value = model.model_validate_json(raw)
        if value.model_dump_json().encode() != raw:
            raise ValueError("Noncanonical state qualification evidence")
        control.checkpoint()
        return value

    @staticmethod
    def checks(
        names: tuple[str, ...], refs: tuple[EvidenceRef, ...], reason: str
    ) -> StateChecks:
        return StateChecks(
            required=names,
            checks=tuple(
                CheckResult(name=n, status="pass", reason_code=reason, evidence=refs)
                for n in names
            ),
        )

    def _environment(
        self, selection: EnvironmentSelection, control: OperationControl
    ) -> tuple[InitialStateSpec, SiteResourceSpec, AdminRecoveryView]:
        selection = EnvironmentSelection.model_validate(selection)
        spec = self.read(
            selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
        )
        if spec != self.specification(selection.scope.task):
            raise ValueError("Unsupported or incomplete Admin state policy")
        site = self.read(
            selection.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
        )
        started = self.read(
            selection.site_started_ref,
            "site-resource-started/1",
            SiteResourceStarted,
            control,
        )
        snapshot = self.snapshot(selection.snapshot_ref, control)
        request, config, scope = snapshot.request, site.configuration, selection.scope
        request.check_site(config)
        if (site.token.owner, request.task, request.operation.attempt_id) != (
            scope.owner,
            scope.task,
            scope.attempt_id,
        ):
            raise OwnershipConflict("Environment changed original snapshot scope")
        binding = self.read(request.binding_ref, "task-binding/1", TaskBinding, control)
        if (binding.identity, binding.baseline_ref) != (scope.task, selection.spec_ref):
            raise OwnershipConflict(
                "Environment changed original task binding/specification"
            )
        service = snapshot.state.plan.service
        expected_layout = AdminInstancePlan(
            files=config.files, apptainer=config.apptainer
        ).layout
        ports = service.ports
        if (
            started.instance.files,
            service.layout,
            (ports.web, ports.database, ports.redis, ports.search, ports.transport),
            service.admin_url,
        ) != (
            config.files,
            expected_layout,
            started.instance.ports,
            started.instance.endpoint,
        ):
            raise OwnershipConflict("Environment changed original instance/image/ports")
        installed = started.ready.worker.installed_sources
        if (installed.release_id, installed.manifest_sha256, installed.executable) != (
            config.installation.manifest.release_id,
            config.installation.manifest_ref.sha256,
            config.installation.python_executable,
        ):
            raise OwnershipConflict("Environment changed original installed worker")
        if snapshot.state.plan.artifacts.paths != tuple(sorted(ARTIFACT_PATHS)):
            raise ValueError(
                "Admin qualification requires all supported artifact paths"
            )
        recovery = self.read(
            site.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        if (
            recovery.owner,
            recovery.attempt_id,
            recovery.baseline_ref,
            recovery.restore_component_id,
            recovery.restore_component_version,
            recovery.state_coverage,
        ) != (
            scope.owner,
            None,
            selection.spec_ref,
            "admin-frontend",
            "1",
            ENVIRONMENT_RESET_CHECKS,
        ):
            raise ValueError(
                "Environment recovery does not support actual frontend reset"
            )
        return spec, site, snapshot

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        spec, site, snapshot = self._environment(selection, control)
        if operation.recovery_ref != site.token.recovery_ref:
            raise OwnershipConflict("Environment record changed original recovery")
        return EnvironmentBaseline(
            scope=selection.scope,
            operation=operation,
            allocation=site.token,
            spec_ref=selection.spec_ref,
            checks=self.checks(
                ENVIRONMENT_CHECKS,
                (
                    reference,
                    selection.site_spec_ref,
                    selection.site_started_ref,
                    selection.snapshot_ref,
                ),
                "ORIGINAL_ADMIN_ENVIRONMENT_MEASURED",
            ),
            measured_state_sha256=snapshot.state.digest,
        )

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
            raise OwnershipConflict("Reset changed original environment plan/scope")
        closures = tuple(
            self.read(ref, "closure-receipt/1", ClosureReceipt, control)
            for ref in selection.closure_refs
        )
        if (
            sum(token.resource_kind == "browser" for token in plan.attempt_allocations)
            != 1
        ):
            raise ValueError("Selected Admin reset needs exactly one original browser")
        if tuple(c.token for c in closures) != plan.attempt_allocations or any(
            c.status != "closed" for c in closures
        ):
            raise OwnershipConflict(
                "Reset needs every original closed attempt resource"
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
        old = snapshot.request
        if (
            request.action != "restore"
            or result.request_sha256 != request.digest
            or request.snapshot_ref != env.snapshot_ref
        ):
            raise OwnershipConflict("Reset changed original restore/snapshot")
        if (
            request.task,
            request.binding_ref,
            request.private_input,
            request.operation.run_id,
            request.operation.owner_id,
            request.operation.attempt_id,
            request.operation.allocation_id,
            request.operation.recovery_ref,
            request.operation.parent_operation_id,
        ) != (
            old.task,
            old.binding_ref,
            old.private_input,
            old.operation.run_id,
            old.operation.owner_id,
            old.operation.attempt_id,
            old.operation.allocation_id,
            plan.task_recovery_ref,
            plan.parent_operation_id,
        ):
            raise OwnershipConflict("Reset changed original task or execution parent")
        restored = self.restored(result.private_result)
        state = restored.state
        if (
            restored.operation,
            restored.task,
            restored.snapshot_ref,
            restored.task_state,
        ) != (request.operation, request.task, env.snapshot_ref, snapshot.task_state):
            raise OwnershipConflict(
                "Reset result differs from original requested restoration"
            )
        if (
            state.snapshot_sha256,
            state.database.sha256,
            state.database.size_bytes,
            state.artifacts,
            state.cache.service,
            state.search.original,
            restored.frontend.service,
        ) != (
            snapshot.state.digest,
            snapshot.state.database.sha256,
            snapshot.state.database.size_bytes,
            snapshot.state.artifacts,
            snapshot.state.plan.service,
            snapshot.state.search,
            snapshot.state.plan.service,
        ):
            raise OwnershipConflict("Restore facts changed original component state")
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
                "Resume does not follow original persisted restore/intent"
            )
        recovered = AdminFrontendRecovered.model_validate_json(resumed.private_result)
        if (
            recovered.stopped != restored.frontend
            or recovered.state_restored_sha256
            != hashlib.sha256(state.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict("Frontend health changed original restored state")
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
            *self.restore_component,
            self.task_reset_checks,
        ):
            raise ValueError("Task recovery cannot omit supported Admin state")
        return QualifiedResetChecks(
            allocation_id=site.token.allocation_id,
            plan=plan,
            spec=spec,
            task_recovery=task_recovery,
            environment_recovery=environment_recovery,
            closures=closures,
            task=self.checks(
                self.task_reset_checks,
                (
                    reference,
                    env.snapshot_ref,
                    selection.restore_request_ref,
                    selection.restore_result_ref,
                    *selection.closure_refs,
                ),
                "ORIGINAL_ADMIN_STATE_RESTORED",
            ),
            environment=self.checks(
                ENVIRONMENT_RESET_CHECKS,
                (
                    reference,
                    selection.resume_request_ref,
                    selection.resume_intent_ref,
                    selection.resume_result_ref,
                ),
                "ORIGINAL_ADMIN_FRONTEND_RESUMED",
            ),
            health=self.checks(
                HEALTH_CHECKS,
                (reference, selection.resume_result_ref),
                "ORIGINAL_ADMIN_SERVICES_HEALTHY",
            ),
        )
