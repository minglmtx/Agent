"""Original preparation/RPC/native/CAS; run/claim/kernel rights remain unit premises."""

from pathlib import Path
from typing import Any, cast
from datetime import datetime, timezone
import pytest
from lab_generate_skill.bootstrap.shopping_category_task_preparation import (
    shopping_category_task_preparation,
)
from lab_generate_skill.bootstrap.shopping_category_records import (
    bind_category_navigation_records,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    assemble_public_context,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.execution import RunBinding, AttemptBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskInputs,
    ExecutionTaskSource,
)
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
    TaskPreparationUnconfirmed,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.evaluators.shopping.navigation import REQUIREMENTS
from shopping_qualification_fixtures import qualified
from preparation_record_fixtures import put, Authority as BindingAuthority
from actor_context_projection_fixtures import actor_projection_case
from context_budget_fixtures import profile
from observation_fixtures import sample_observation
from retrieval_fixtures import reference
from test_actor_protocol import turn
from test_slurm_commands import guard
from shopping_prepared_family_fixtures import prepared_family_case
from shopping_navigation_equivalence_fixtures import baseline, source
from shopping_category_initialization_port_fixtures import initialize_current
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.lifecycle import ClosureReceipt


class UnitPreparationAuthority:
    """Check original persisted requests; this is not live source permission."""

    def __init__(self, denied: bool) -> None:
        self.denied = denied
        self.preparation: RecordedSiteTaskPreparation | None = None
        self.calls = 0

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.denied:
            raise PermissionError("unit category source denied")
        assert declaration.scope.task == plan.intent.binding.task
        if self.preparation is not None:
            for request, ref in (
                (
                    self.preparation.state.snapshot_request,
                    self.preparation.state.snapshot_request_ref,
                ),
                (
                    self.preparation.state.prepare_request,
                    self.preparation.state.prepare_request_ref,
                ),
            ):
                if request is not None and operation == request.operation:
                    assert ref is not None
                    assert (
                        self.preparation.reads.read(ref, control)
                        == request.model_dump_json().encode()
                    )


def producer(
    c: dict[str, Any],
    patch: pytest.MonkeyPatch,
    fault: str,
    saved: dict[str, Any],
    source_inputs: PublicContextInputs | None = None,
) -> dict[str, Any]:
    site, store, live, scope, template = (
        c["c"],
        c["store"],
        c["live"],
        c["scope"],
        c["template"],
    )
    original_intent = ResourceAcquisitionIntent.model_validate_json(
        store.read(
            site.journal.read(site.spec.token, site.op).events[1].evidence[0],
            control=guard(),
        )
    )
    stopped = False
    bind = site.controls.bind

    class Control:
        def __init__(self, value: OperationControl, execution: bool) -> None:
            self.value, self.execution = value, execution

        def checkpoint(self) -> float:
            if stopped and self.execution:
                raise OperationStopped("CANCELLED", "category-preparation-caller")
            return self.value.checkpoint()

        def wait(self, seconds: float) -> None:
            self.checkpoint()
            self.value.wait(seconds)
            self.checkpoint()

    def controls(op: OperationContext) -> OperationControl:
        return Control(bind(op), op.mode == "execute")

    patch.setattr(site.controls, "bind", controls)
    requests: list[SiteTaskRequest] = []

    def native(
        request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        nonlocal stopped
        requests.append(request)
        result = SiteTaskResult.model_validate(
            c["worker"].execute_task(request, control=control)
        )
        if fault == "cancel-after-snapshot" and request.action == "snapshot":
            stopped = True
        return result

    # Replace only the explicit simulated worker boundary. Real service/client
    # framing, journal and canonical request/result persistence stay selected.
    patch.setattr(site.channels[0].engine, "execute_task", native)
    patch.setattr(site.channels[0].engine, "stop", c["worker"].instance.stop)
    params = reference(
        LocalActorParameters(
            max_input_tokens=61440,
            max_new_tokens=4096,
            seed=0,
            temperature=0.7,
            top_p=0.95,
        ),
        "model-parameters/1",
        store=store,
    )
    context = ActorContextConfiguration(
        policy=actor_projection_case("shopping").policy,
        profiles=(
            profile(
                provider="fixed-actor-worker",
                configuration_ref=params,
                context_window=65536,
                output_reserve=4096,
                input_limit=61440,
                soft_target=24576,
            ),
        ),
    )
    t = turn()
    policy = EngineeringActorPolicy(
        skill=t.skill,
        memory=t.memory,
        max_generations=1,
        max_interactions=1,
        actor_projection=FullAxProjection(),
        actor_context_ref=put(store, context),
        candidate_id="category-producer-unit",
        revision_round=0,
    )
    public = PublicConstructionContext(
        context_id="unit-upstream",
        task=c["public"],
        initial_observation_ref=put(store, sample_observation(scope.task), "public"),
    )
    if source_inputs is not None:
        source_op = source_inputs.baseline.operation.model_copy(
            update={
                "operation_id": "historical-context-freeze",
                "attempt_id": None,
                "allocation_id": None,
                "recovery_ref": None,
            }
        )
        source_receipt = assemble_public_context(source_inputs, source_op)
        source_ref = put(store, source_receipt)
        public = source_inputs.context
    else:
        source_ref = reference(
            {"unit_source_permission_premise": True},
            "public-context-receipt/1",
            store=store,
        )
    inputs = ExecutionTaskInputs(
        task_binding_ref=template.binding_ref,
        source_context_receipt_ref=source_ref,
        skill_ref=put(store, t.skill, "public"),
        attempt_id=scope.attempt_id,
    )
    base = template.operation.model_copy(
        update={
            "operation_id": "category-producer",
            "allocation_id": None,
            "recovery_ref": None,
        }
    )
    run = RunBinding(
        owner=scope.owner,
        plan_ref=reference({"unit_run_premise": True}, "run-plan/1", store=store),
        release_ref=site.spec.configuration.installation.manifest_ref,
        submission_key="category-unit",
    )
    binding = AttemptBinding(
        run=run,
        attempt_id=scope.attempt_id,
        task=scope.task,
        claim_ref=reference(
            {"unit_claim_premise": True}, "source-claim/1", store=store
        ),
    )
    intent = TaskAttemptIntent(
        schema_version="execution-task-intent/1",
        binding=binding,
        skill_digest=t.skill.content_digest,
        public_context_ref=put(store, public, "public"),
        execution_policy_ref=put(store, policy),
        execution_inputs_ref=put(store, inputs),
    )
    declaration = SiteTaskPreparationPlan(
        scope=scope,
        site_spec_ref=original_intent.configuration_ref,
        task_binding_ref=template.binding_ref,
        private_input_ref=store.put(
            template.private_input.encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="shopping-category-execution-input/1",
                visibility="private",
                producer="unit",
            ),
            control=guard(),
        ),
        snapshot_schema="shopping-category-recovery/1",
        snapshot_operation=template.operation,
        prepare_operation=template.operation.model_copy(
            update={"operation_id": "prepare"}
        ),
        environment_operation=template.operation.model_copy(
            update={
                "operation_id": "environment",
                "recovery_ref": site.spec.token.recovery_ref,
            }
        ),
        resource_read_operation=site.op.cleanup(
            "category-resource-read", now=datetime.now(timezone.utc), seconds=30
        ),
    )
    plan = TaskExecutionPlan(
        schema_version="task-execution-plan/2",
        intent=intent,
        reset_plan_ref=c["plan_ref"],
        declaration_ref=put(store, declaration),
        skill_ref=inputs.skill_ref,
        evaluation=EvaluationContract(
            identity=scope.task,
            attempt_id=scope.attempt_id,
            task_contract_ref=template.binding_ref,
            public_task_ref=c["binding"].public_task_ref,
            completion_spec_ref=c["binding"].private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        ),
        operation=base,
        read_operation=base.model_copy(
            update={"operation_id": "category-producer-read", "attempt_id": None}
        ),
        cleanup_seconds=30,
        source_ref=put(
            store,
            ExecutionTaskSource(
                run=run,
                task=c["binding"],
                intent=intent,
                source_context_receipt_ref=inputs.source_context_receipt_ref,
            ),
        ),
    )
    authority = UnitPreparationAuthority(fault == "source-denied")
    bindings = bind_category_navigation_records(
        store, site.controls, BindingAuthority()
    )
    if fault == "none":
        with pytest.raises(ValueError, match="snapshot codec"):
            shopping_category_task_preparation(
                plan,
                declaration.model_copy(
                    update={"snapshot_schema": "admin-navigation-recovery/1"}
                ),
                site.spec,
                live,
                site.journal,
                store,
                site.controls,
                bindings,
                authority,
            )
        with pytest.raises(ValueError, match="authorities"):
            shopping_category_task_preparation(
                plan,
                declaration,
                site.spec,
                live,
                site.journal,
                store,
                site.controls,
                bindings,
                cast(Any, None),
            )
        assert not requests
    preparer = shopping_category_task_preparation(
        plan,
        declaration,
        site.spec,
        live,
        site.journal,
        store,
        site.controls,
        bindings,
        authority,
    )
    authority.preparation = preparer
    saved.update(
        preparer=preparer, requests=requests, case=site, worker=c["worker"], plan=plan
    )
    original_put = store.put

    def publish(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if (
            fault == "prepared-write"
            and metadata.content_schema == "site-task-prepared/2"
        ):
            raise OSError("unit prepared publication failure")
        return EvidenceRef.model_validate(
            original_put(raw, metadata, control=control, exchange_id=exchange_id)
        )

    patch.setattr(store, "put", publish)
    for phase, method in (
        ("acquiring", preparer.acquire),
        ("preparing", preparer.prepare),
    ):
        op = OperationContext.model_validate(
            base.model_copy(update={"operation_id": base.operation_id + "." + phase})
        )
        method(plan, op, site.controls.bind(op))
    state = preparer.state
    assert (
        state.result is not None
        and state.result_ref is not None
        and state.snapshot_result is not None
    )
    assert state.prepare_request is not None and state.prepare_result is not None
    assert (
        state.environment_ref is not None
        and state.environment_selection_ref is not None
    )
    assert [r.action for r in requests] == ["snapshot", "prepare"]
    with pytest.raises(DispatchAlreadyCommitted):
        preparer.prepare(plan, base, site.controls.bind(base))
    return dict(
        snapshot_result=state.snapshot_result,
        environment_selection_ref=state.environment_selection_ref,
        environment_ref=state.environment_ref,
        prepare_request=state.prepare_request,
        prepare_result=state.prepare_result,
        producer=preparer,
        plan=plan,
        declaration=declaration,
        source_inputs=source_inputs,
        source_context_ref=source_ref,
        parameters_ref=params,
        actor_context_ref=policy.actor_context_ref,
    )


def preparation_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, original: Any, fault: str
) -> dict[str, Any]:
    saved: dict[str, Any] = {}

    def prepared(c: dict[str, Any]) -> dict[str, Any]:
        return producer(c, patch, fault, saved)

    if fault == "none":
        with qualified(
            root,
            node,
            patch,
            category=(original[0], original[2]),
            prepare_with=prepared,
        ) as c:
            assert saved["preparer"].state.phase == "prepared"
            saved["result"] = saved["preparer"].state.result
    else:
        with pytest.raises(TaskPreparationUnconfirmed) as error:
            with qualified(
                root,
                node,
                patch,
                category=(original[0], original[2]),
                prepare_with=prepared,
            ):
                raise AssertionError("failed preparation reached qualification")
        saved["failure"] = error.value
        assert saved["preparer"].state.phase == "quarantined"
        count = len(saved["requests"])
        plan = saved["plan"]
        with pytest.raises(DispatchAlreadyCommitted):
            saved["preparer"].prepare(plan, plan.operation, guard())
        assert len(saved["requests"]) == count
    site = saved["case"]
    ending = site.op.cleanup(
        "category-producer-ending-read", now=datetime.now(timezone.utc), seconds=30
    )
    record = site.journal.read(site.spec.token, ending)
    assert record.state == "closed"
    saved["resource_closed"] = True
    return saved


def combined_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, original: Any, fault: str
) -> dict[str, Any]:
    saved: dict[str, Any] = {}

    def prepared(c: dict[str, Any]) -> dict[str, Any]:
        historical_scope = c["scope"].model_copy(
            update={
                "attempt_id": "historical-category",
                "context_id": "historical-context",
            }
        )
        historical = source(
            baseline(
                node / "independent-source",
                c["store"],
                (original[0], None, c["public"]),
                scope_override=historical_scope,
            ),
            c["store"],
            scoped=True,
        )
        for ref in dict.fromkeys(evidence_references(historical)):
            c["store"].read(ref, control=guard())
        saved["source_frozen_before_candidate_snapshot"] = True
        return producer(c, patch, "none", saved, historical)

    def bound(c: dict[str, Any]) -> ClosureReceipt:
        produced = c["recorded_preparation"]
        preparer = produced["producer"]
        state = preparer.state
        assert state.result_ref is not None and state.result is not None
        assert (
            c["store"].read(state.result_ref, control=guard())
            == state.result.model_dump_json().encode()
        )
        assert c["publication"] == state.result.publication
        assert (
            c["browser_owner"].spec.configuration.initialization.site_ref
            == state.original_acquired().site_started_ref
        )
        frozen = preparer.plan.model_dump_json()
        closure = initialize_current(
            c,
            patch,
            fault,
            saved,
            preparer.plan,
            state.result_ref,
            produced["source_context_ref"],
            produced["parameters_ref"],
            produced["actor_context_ref"],
            produced["source_inputs"].baseline.scope.attempt_id,
        )
        assert preparer.plan.model_dump_json() == frozen
        assert [request.action for request in saved["requests"]] == [
            "snapshot",
            "prepare",
        ]
        saved["actual_prepared_result_ref"] = state.result_ref
        return closure

    prepared_family_case(
        root,
        node,
        patch,
        "none",
        category=(original[0], original[2]),
        retain_browser=True,
        prepare_with=prepared,
        on_bound=bound,
    )
    return saved
