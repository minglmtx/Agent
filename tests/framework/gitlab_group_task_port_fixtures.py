"""Current Group ports with original native codecs and explicit physical doubles.

The registered RPC, CAS, complete tree snapshot and restore predicates are real
code. SQL/services/kernel/source permissions are unit premises, never live grants.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.resource_records import put as resource_put
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.bootstrap.gitlab_group_records import bind_group_records
from lab_generate_skill.bootstrap.gitlab_group_source import GroupSourceSelection
from lab_generate_skill.bootstrap.gitlab_group_task_preparation import (
    gitlab_group_task_preparation,
)
from lab_generate_skill.domain.construction import AttemptIntent
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.execution import AttemptBinding, RunBinding
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.sites.gitlab.tasks.group_resume import GroupResume
from generator_worker_fixtures import unit_guard
from gitlab_native_fixtures import Lease
from gitlab_group_lifecycle_fixtures import case as native_case, Case as NativeCase
from gitlab_group_source_fixtures import source_case, original_bytes
from preparation_record_fixtures import Authority, put
from site_resource_fixtures import ResourceInstance, ResourceChannel, Case
from site_worker_fixtures import sources
from test_core_contracts import reference
from test_gitlab_group_source_composition import contracts_for


class UnitPreparationAuthority:
    denied = False

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Explicit Group unit source denial")
        assert plan.intent.binding.task == declaration.scope.task
        assert plan.intent.binding.attempt_id == declaration.scope.attempt_id


@dataclass
class GroupPortCase:
    resource: Case
    scope: StateScope
    site: RetainedSiteResource
    plan: TaskExecutionPlan
    declaration: SiteTaskPreparationPlan
    reset: ResetPlan
    preparation: RecordedSiteTaskPreparation
    authority: UnitPreparationAuthority
    requests: list[SiteTaskRequest]
    natives: list[NativeCase]
    bindings: TaskBindings
    cleanup_operations: dict[str, OperationContext] = field(default_factory=dict)

    def cleanup(self, name: str) -> OperationContext:
        if name not in self.cleanup_operations:
            self.cleanup_operations[name] = self.plan.operation.cleanup(
                name, now=self.resource.clock.utcnow(), seconds=30
            )
        return self.cleanup_operations[name]

    def operation(self, name: str) -> OperationContext:
        return self.plan.operation.model_copy(
            update={"operation_id": self.plan.operation.operation_id + "." + name}
        )

    @property
    def workspace(self) -> Path:
        return Path(self.resource.spec.configuration.files.workspace_root)

    @property
    def binding(self) -> EvidenceRef:
        return self.declaration.task_binding_ref

    def acquire(self) -> tuple[EvidenceRef, ...]:
        op = self.operation("acquiring")
        return self.preparation.acquire(self.plan, op, self.resource.controls.bind(op))

    def prepare(self) -> tuple[EvidenceRef, ...]:
        op = self.operation("preparing")
        return self.preparation.prepare(self.plan, op, self.resource.controls.bind(op))


@contextmanager
def group_port_case(
    root: Path,
    node: Path,
    patch: pytest.MonkeyPatch,
    source: str,
    *,
    explicit_origin: bool = False,
) -> Iterator[GroupPortCase]:
    contracts = contracts_for(source)
    owner, c = source_case(
        root,
        node,
        patch,
        contracts,
        attempt_id="attempt",
        explicit_origin=explicit_origin,
    )
    scope = owner.scope
    store, controls = c.evidence, c.controls
    spec = group_initial_spec(scope.task)
    spec_ref = put(store, spec)
    environment = RecoveryPlan(
        recovery_id="group-environment",
        owner=scope.owner,
        baseline_ref=spec_ref,
        restore_component_id="gitlab-services",
        restore_component_version="1",
        state_coverage=spec.environment_reset_checks,
    )
    token = c.spec.token.model_copy(update={"recovery_ref": put(store, environment)})
    c.spec = SiteResourceSpec.model_validate(
        c.spec.model_copy(
            update={
                "configuration": c.spec.configuration.model_copy(
                    update={"token": token}
                )
            }
        )
    )
    c.op = c.op.model_copy(update={"recovery_ref": token.recovery_ref})
    _, native_ref, template = contracts[0]
    raw = original_bytes()[native_ref.sha256]
    public = GroupSourceSelection(raw, template).public_at(
        "http://127.0.0.1:" + str(Lease.ports[0]) + "/", None
    )
    private = GroupSourceSelection(raw, template).load(native_ref, public)
    from gitlab_group_source_fixtures import retain

    retain(store, raw, native_ref)
    binding = TaskBinding(
        identity=scope.task,
        registration_id="engineering-gitlab-group-creation",
        public_task_ref=put(store, public, "public"),
        private_spec_ref=put(store, private),
        baseline_ref=spec_ref,
    )
    bindings = bind_group_records(store, controls, Authority())
    binding_ref = bindings.publish(binding, c.op)
    task_recovery = RecoveryPlan(
        recovery_id="group-task-recovery",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=spec_ref,
        restore_component_id="gitlab-group-creation",
        restore_component_version="1",
        state_coverage=spec.task_reset_checks,
    )
    task_recovery_ref = put(store, task_recovery)
    browser_recovery = RecoveryPlan(
        recovery_id="group-browser-close",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=spec_ref,
        restore_component_id="browser-close",
        restore_component_version="1",
        state_coverage=("browser-processes",),
    )
    browser = AllocationToken(
        allocation_id="group-browser",
        owner=scope.owner,
        scope="attempt",
        attempt_id=scope.attempt_id,
        resource_kind="browser",
        expected_resource_id="unit-group-browser",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=put(store, browser_recovery),
    )
    operation = OperationContext(
        operation_id="group-task",
        run_id=scope.owner.run_id,
        owner_id=scope.owner.owner_id,
        attempt_id=scope.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
    )

    def native_operation(name: str, recovery: EvidenceRef) -> OperationContext:
        return operation.model_copy(
            update={
                "operation_id": "group-native-" + name,
                "allocation_id": token.allocation_id,
                "recovery_ref": recovery,
            }
        )

    snapshot_op = native_operation("snapshot", task_recovery_ref)
    prepare_op = native_operation("prepare", task_recovery_ref)
    reset = ResetPlan(
        scope=scope,
        parent_operation_id=prepare_op.operation_id,
        spec_ref=spec_ref,
        task_recovery_ref=task_recovery_ref,
        environment_recovery_ref=token.recovery_ref,
        attempt_allocations=(browser,),
    )
    declaration = SiteTaskPreparationPlan(
        scope=scope,
        site_spec_ref=resource_put(
            store,
            c.spec.model_dump_json().encode(),
            c.spec.schema_version,
            controls.bind(c.op),
        ),
        task_binding_ref=binding_ref,
        private_input_ref=binding.private_spec_ref,
        snapshot_schema="gitlab-group-recovery/1",
        snapshot_operation=snapshot_op,
        prepare_operation=prepare_op,
        environment_operation=native_operation("environment", token.recovery_ref),
        resource_read_operation=c.op.cleanup(
            "group-held-read", now=c.clock.utcnow(), seconds=120
        ),
    )
    skill = put(
        store,
        CompactSkill(
            title="Create group",
            principle="Inspect and save the requested group.",
            when_to_apply="When creating the requested local group.",
        ),
        "public",
    )
    run = RunBinding(
        owner=scope.owner,
        plan_ref=reference("private", "run-plan/1"),
        release_ref=reference("private", "release-manifest/1"),
        submission_key="group-unit-only",
    )
    intent = AttemptIntent(
        binding=AttemptBinding(
            run=run,
            task=scope.task,
            attempt_id=scope.attempt_id,
            claim_ref=reference("private", "source-claim/1"),
        ),
        candidate_slot=0,
        skill_digest=skill.sha256,
        public_context_ref=reference("public", "public-construction-context/1"),
    )
    evaluation = EvaluationContract(
        identity=scope.task,
        attempt_id=scope.attempt_id,
        task_contract_ref=binding_ref,
        public_task_ref=binding.public_task_ref,
        completion_spec_ref=binding.private_spec_ref,
        scope="engineering",
        requirements=EvidenceRequirements(events=("terminal",)),
    )
    plan = TaskExecutionPlan(
        intent=intent,
        reset_plan_ref=put(store, reset),
        declaration_ref=put(store, declaration),
        skill_ref=skill,
        evaluation=evaluation,
        operation=operation,
        read_operation=operation.model_copy(
            update={"operation_id": "group-task-read", "attempt_id": None}
        ),
        cleanup_seconds=30,
    )
    requests: list[SiteTaskRequest] = []
    natives: list[NativeCase] = []

    class Native(ResourceInstance):
        primitive: NativeCase

        def start(self, control: OperationControl) -> SiteInstanceStarted:
            super().start(control)
            self.primitive = native_case(
                Path(c.spec.configuration.files.node_root).parent,
                configured=c.spec.configuration,
                owner_guard=unit_guard(current_process_identity(), control),
            )
            self.primitive.artifacts.store = store
            natives.append(self.primitive)
            return self.primitive.artifacts.context.instance

        def execute_task(
            self, request: SiteTaskRequest, *, control: OperationControl
        ) -> SiteTaskResult:
            requests.append(request)
            return self.primitive.task.execute_task(request, control=control)

        def capture_task(
            self, request: SiteCaptureRequest, *, control: OperationControl
        ) -> SiteTaskResult:
            return self.primitive.task.capture_task(request, control=control)

        def resume_frontend(
            self, request: Any, *, control: OperationControl
        ) -> SiteResumeResult:
            return GroupResume(self.primitive.task).resume_frontend(
                request, control=control
            )

        def stop(self, control: OperationControl) -> Any:
            super().stop(control)
            return self.primitive.task.instance.stop(control)

    original_channel = ResourceChannel.__init__

    def channel(self: Any, case: Case) -> None:
        original_channel(self, case)
        self.engine = Native(case)
        self.service = SiteService(
            lambda configuration: self.engine, sources, unit_guard
        )

    patch.setattr(ResourceChannel, "__init__", channel)
    site = RetainedSiteResource(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=store,
        controls=controls,
        clock=c.clock,
        authority=c.authority,
    )
    authority = UnitPreparationAuthority()
    preparation = gitlab_group_task_preparation(
        plan, declaration, c.spec, site, c.journal, store, controls, bindings, authority
    )
    try:
        yield GroupPortCase(
            c,
            scope,
            site,
            plan,
            declaration,
            reset,
            preparation,
            authority,
            requests,
            natives,
            bindings,
        )
    finally:
        if site.phase == "open":
            close = c.op.cleanup(
                "unit-group-final-close", now=c.clock.utcnow(), seconds=30
            )
            site.close(close, controls.bind(close))
