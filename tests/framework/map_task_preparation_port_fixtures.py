"""Real registered RPC/CAS/native files; explicit synthetic services/rights."""

from collections.abc import Iterator, Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.resource import RegisteredSite, registered_site
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.resource_records import put as resource_put
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.ports.site_resources import SiteResourceAuthority
from site_resource_fixtures import Case
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.bootstrap.map_task_preparation import map_task_preparation
from lab_generate_skill.domain.construction import AttemptIntent
from lab_generate_skill.domain.execution import AttemptBinding, RunBinding
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.ports.lifecycle import OperationControl
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_source_fixtures import selection
from map_navigation_group_cases import SOURCES
from map_navigation_evaluation_fixtures import bind_original_contract
from map_qualification_fixtures import configure_qualification
from map_qualified_source_native import MapQualifiedSource
from map_source_inputs import MapSourceInputs
from map_source_native_boundary_fixtures import (
    source_native_boundary,
    source_native_ports,
)
from preparation_record_fixtures import put
from test_core_contracts import reference
from test_site_resource import enter
from test_slurm_commands import guard


class UnitPreparationAuthority:
    """Explicit unit premise only; never a production admission implementation."""

    def __init__(self, c: RegisteredMapCase) -> None:
        self.c = c
        self.denied = False
        self.preparation: RecordedSiteTaskPreparation | None = None

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("synthetic source admission denied")
        assert declaration.scope == self.c.scope
        assert plan.intent.binding.attempt_id == self.c.scope.attempt_id
        prep = self.preparation
        if prep is not None:
            for request, ref in (
                (prep.state.snapshot_request, prep.state.snapshot_request_ref),
                (prep.state.prepare_request, prep.state.prepare_request_ref),
            ):
                if request is not None and operation == request.operation:
                    assert ref is not None
                    assert (
                        self.c.resource.evidence.read(ref, control=control)
                        == request.model_dump_json().encode()
                    )


@dataclass
class MapPreparationPortCase:
    original: RegisteredMapCase
    site: SiteHandle
    source: MapQualifiedSource
    plan: TaskExecutionPlan
    declaration: SiteTaskPreparationPlan
    reset: ResetPlan
    reset_ref: EvidenceRef
    authority: UnitPreparationAuthority
    preparation: RecordedSiteTaskPreparation
    requests: list[SiteTaskRequest]

    def operation(self, name: str) -> OperationContext:
        return self.plan.operation.model_copy(
            update={"operation_id": self.plan.operation.operation_id + "." + name}
        )

    def acquire(self) -> tuple[EvidenceRef, ...]:
        op = self.operation("acquiring")
        return self.preparation.acquire(
            self.plan, op, self.original.resource.controls.bind(op)
        )

    def prepare(self) -> tuple[EvidenceRef, ...]:
        op = self.operation("preparing")
        return self.preparation.prepare(
            self.plan, op, self.original.resource.controls.bind(op)
        )


@contextmanager
def preparation_case(
    root: Path,
    patch: pytest.MonkeyPatch,
    source_id: str = SOURCES[0],
    *,
    site_authority_factory: Callable[[Case], SiteResourceAuthority] | None = None,
    deferred_site: bool = False,
) -> Iterator[MapPreparationPortCase]:
    c = RegisteredMapCase(root, patch, navigation_source=source_id)
    try:
        bind_original_contract(c)
        spec_ref, _ = configure_qualification(c, patch)
        inputs = MapSourceInputs(
            c.configuration, c.private, None, spec_ref, None, selection(source_id)
        )
        if deferred_site:
            if site_authority_factory is None:
                raise ValueError(
                    "Deferred current site requires explicit original source factory"
                )
            owner = RetainedSiteResource(
                c.resource.spec,
                c.resource.op,
                journal=c.resource.journal,
                evidence=c.resource.evidence,
                controls=c.resource.controls,
                clock=c.resource.clock,
                authority=site_authority_factory(c.resource),
            )
            # Public URL is a declared synthetic unit origin, never an invented
            # startup receipt. The original acquired instance is checked later.
            endpoint = "http://127.0.0.1:" + str(c.case.spec.ports.web) + "/"
            source = MapQualifiedSource(
                c.resource,
                owner,
                inputs,
                allowed_actions=("click", "send_msg_to_user"),
                declared_endpoint=endpoint,
            )
            n = source.native
            c.binding, c.task_recovery = n.binding_ref, n.recovery_ref
            p = bind_preparation(c, owner, source, patch)
            original_open = owner.open

            def acquired(control: OperationControl) -> RegisteredSite:
                live = original_open(control)
                assert live.site.instance.endpoint == endpoint
                source_native_ports(c, source, patch, [])
                count_requests(p, live, patch)
                return live

            patch.setattr(owner, "open", acquired)
            try:
                yield p
            finally:
                if owner.phase == "open":
                    op = c.resource.op.cleanup(
                        "unit-finally-site-close",
                        now=datetime.now(timezone.utc),
                        seconds=30,
                    )
                    owner.close(op, c.resource.controls.bind(op))
            return
        manager = (
            enter(c.resource)
            if site_authority_factory is None
            else registered_site(
                c.resource.spec,
                c.resource.op,
                journal=c.resource.journal,
                evidence=c.resource.evidence,
                controls=c.resource.controls,
                clock=c.resource.clock,
                authority=site_authority_factory(c.resource),
            )
        )
        with manager as live:
            source = MapQualifiedSource(
                c.resource, live, inputs, allowed_actions=("click", "send_msg_to_user")
            )
            n = source.native
            c.binding, c.task_recovery = n.binding_ref, n.recovery_ref
            source_native_boundary(c, source, patch, [])
            yield bind_preparation(c, live, source, patch)
    finally:
        c.close_sockets()


def bind_preparation(
    c: RegisteredMapCase,
    live: SiteHandle,
    source: MapQualifiedSource,
    patch: pytest.MonkeyPatch,
    *,
    execution_seconds: int = 120,
) -> MapPreparationPortCase:
    """Declare current port on this exact already-acquired original site."""
    n = source.native
    deadline = datetime.now(timezone.utc) + timedelta(seconds=execution_seconds)
    execute = OperationContext(
        operation_id="construction-task",
        run_id=c.scope.owner.run_id,
        owner_id=c.scope.owner.owner_id,
        attempt_id=c.scope.attempt_id,
        deadline=deadline,
    )

    def native_op(name: str, recovery: EvidenceRef) -> OperationContext:
        return execute.model_copy(
            update={
                "operation_id": name,
                "allocation_id": c.resource.spec.token.allocation_id,
                "recovery_ref": recovery,
            }
        )

    snapshot_op = native_op("construction-native-snapshot", n.recovery_ref)
    prepare_op = native_op("construction-native-prepare", n.recovery_ref)
    environment_op = native_op(
        "construction-native-environment", c.resource.spec.token.recovery_ref
    )
    browser_recovery = RecoveryPlan(
        recovery_id="browser-close",
        owner=c.scope.owner,
        attempt_id=c.scope.attempt_id,
        baseline_ref=n.spec_ref,
        restore_component_id="browser-close",
        restore_component_version="1",
        state_coverage=("browser-processes",),
    )
    browser = AllocationToken(
        allocation_id="browser-allocation",
        owner=c.scope.owner,
        scope="attempt",
        attempt_id=c.scope.attempt_id,
        resource_kind="browser",
        expected_resource_id="browser-instance",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=put(c.resource.evidence, browser_recovery),
    )
    reset = ResetPlan(
        scope=c.scope,
        parent_operation_id=prepare_op.operation_id,
        spec_ref=n.spec_ref,
        task_recovery_ref=n.recovery_ref,
        environment_recovery_ref=c.resource.spec.token.recovery_ref,
        attempt_allocations=(browser,),
    )
    reset_ref = put(c.resource.evidence, reset)
    site_spec_ref = resource_put(
        c.resource.evidence,
        c.resource.spec.model_dump_json().encode(),
        c.resource.spec.schema_version,
        guard(30),
    )
    declaration = SiteTaskPreparationPlan(
        scope=c.scope,
        site_spec_ref=site_spec_ref,
        task_binding_ref=n.binding_ref,
        private_input_ref=n.binding.private_spec_ref,
        snapshot_schema="map-navigation-snapshot/1",
        snapshot_operation=snapshot_op,
        prepare_operation=prepare_op,
        environment_operation=environment_op,
        resource_read_operation=c.resource.op.cleanup(
            "preparation-held-resource-read",
            now=datetime.now(timezone.utc),
            seconds=90,
        ),
    )
    run = RunBinding(
        owner=c.scope.owner,
        plan_ref=reference("private", "run-plan/1"),
        release_ref=reference("private", "release-manifest/1"),
        submission_key="unit-only-source",
    )
    skill = CompactSkill(
        title="Navigate",
        principle="1. Inspect the current target and open it.",
        when_to_apply="When navigating to the requested local page.",
    )
    skill_ref = put(c.resource.evidence, skill, "public")
    intent = AttemptIntent(
        binding=AttemptBinding(
            run=run,
            task=c.scope.task,
            attempt_id=c.scope.attempt_id,
            claim_ref=reference("private", "source-claim/1"),
        ),
        candidate_slot=0,
        skill_digest=skill_ref.sha256,
        public_context_ref=reference("public", "public-construction-context/1"),
    )
    evaluation = EvaluationContract(
        identity=c.scope.task,
        attempt_id=c.scope.attempt_id,
        task_contract_ref=n.binding_ref,
        public_task_ref=n.binding.public_task_ref,
        completion_spec_ref=n.binding.private_spec_ref,
        scope="engineering",
        requirements=EvidenceRequirements(events=("terminal",)),
    )
    plan = TaskExecutionPlan(
        intent=intent,
        reset_plan_ref=reset_ref,
        declaration_ref=put(c.resource.evidence, declaration),
        skill_ref=skill_ref,
        evaluation=evaluation,
        operation=execute,
        read_operation=execute.model_copy(
            update={"operation_id": "unit-run-read", "attempt_id": None}
        ),
        cleanup_seconds=30,
    )
    authority = UnitPreparationAuthority(c)
    prep = map_task_preparation(
        plan,
        declaration,
        c.resource.spec,
        live,
        c.resource.journal,
        c.resource.evidence,
        c.resource.controls,
        n.bindings,
        authority,
    )
    authority.preparation = prep
    requests: list[SiteTaskRequest] = []
    result = MapPreparationPortCase(
        c, live, source, plan, declaration, reset, reset_ref, authority, prep, requests
    )
    if isinstance(live, RegisteredSite):
        count_requests(result, live, patch)
    return result


def count_requests(
    p: MapPreparationPortCase, live: SiteHandle, patch: pytest.MonkeyPatch
) -> None:
    original = live.tasks.execute_task

    def counted(
        request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        p.requests.append(request)
        return original(request, control=control)

    patch.setattr(live.tasks, "execute_task", counted)
