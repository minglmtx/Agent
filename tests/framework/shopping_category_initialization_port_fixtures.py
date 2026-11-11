"""Whole initializer on native-produced bytes and registered browser records.

Upstream run/claim/task-prepared adoption and historical Reset are explicit unit
premises. Native contents come from independent fixture workers; native SQL,
DOM/kernel/model permissions remain doubles. No actual source/run grant.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_task_initialization import (
    shopping_category_task_initialization,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.errors import EvidenceNotFound
from lab_generate_skill.domain.execution import RunBinding, AttemptBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskInputs,
    ExecutionTaskSource,
)
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import (
    SiteTaskPreparationPlan,
    SiteTaskPrepared,
)
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.task_initialization import (
    TaskInitializationPlan,
    TaskActorInitialization,
)
from lab_generate_skill.domain.initialization_admission_inputs import (
    InitializationAdmissionInputs,
)
from lab_generate_skill.domain.public_context import assemble_public_context
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.lifecycle import (
    ClosureReceipt,
    AllocationToken,
    RecoveryPlan,
    OperationContext,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_equivalence import (
    CategoryNavigationInitialComparison,
)
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from lab_generate_skill.evaluators.shopping.navigation import REQUIREMENTS
from actor_context_projection_fixtures import actor_projection_case
from context_budget_fixtures import profile
from browser_resource_fixtures import ResourceChannel
from shopping_prepared_family_fixtures import prepared_family_case
from shopping_navigation_equivalence_fixtures import baseline, source
from shopping_category_browser_fixtures import Page
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from test_actor_protocol import turn
from test_browser_capture import Authority as CaptureAuthority
from task_initialization_port_fixtures import (
    UnitInitializationAuthority,
    UnitNavigationContextAuthority,
    UnitInitialAuthority,
)
from test_slurm_commands import guard


def initialize_current(
    c: dict[str, Any],
    patch: pytest.MonkeyPatch,
    fault: str,
    saved: dict[str, Any],
    plan: TaskExecutionPlan,
    prepared_result_ref: EvidenceRef,
    source_context_ref: EvidenceRef,
    parameters_ref: EvidenceRef,
    actor_context_ref: EvidenceRef,
    source_attempt: str,
) -> ClosureReceipt:
    b, owner, store, scope = (
        c["browser_case"],
        c["browser_owner"],
        c["store"],
        c["scope"],
    )
    base, context_ref, parameters = plan.operation, source_context_ref, parameters_ref
    assert plan.intent.execution_policy_ref is not None
    policy = EngineeringActorPolicy.model_validate_json(
        store.read(plan.intent.execution_policy_ref, control=guard())
    )
    assert policy.actor_context_ref == actor_context_ref
    recovery = RecoveryPlan(
        recovery_id="category-unit-model",
        owner=scope.owner,
        baseline_ref=c["spec_ref"],
        restore_component_id="unit-model",
        restore_component_version="1",
        state_coverage=("unit-model",),
    )
    token = AllocationToken(
        allocation_id="category-unit-model",
        owner=scope.owner,
        scope="batch",
        resource_kind="actor",
        expected_resource_id="unit-model",
        provider_id="fixed-actor-worker",
        provider_version="1",
        recovery_ref=put(store, recovery),
    )
    actor = TaskActorInitialization(
        candidate_id=policy.candidate_id,
        revision_round=policy.revision_round,
        context_configuration_ref=actor_context_ref,
        memory=policy.memory,
        model_allocation=token,
        parameters_refs=(parameters,),
        generation_seconds=30,
        interaction_seconds=30,
        cleanup_seconds=30,
    )

    def operation(name: str) -> OperationContext:
        return OperationContext.model_validate(
            base.model_copy(update={"operation_id": "category-initial-" + name})
        )

    d = TaskInitializationPlan(
        scope=scope,
        prepared_result_ref=prepared_result_ref,
        source_context_receipt_ref=context_ref,
        browser_spec_ref=put(store, b.spec),
        browser_acquisition=b.op,
        capture_operation=b.op.model_copy(
            update={"operation_id": "category-passive-first"}
        ),
        initial_operation=operation("checks"),
        baseline_operation=operation("baseline"),
        comparison_operation=operation("comparison"),
        equivalence_operation=operation("equivalence"),
        actor=actor,
    )
    stopped = False
    capture_calls: list[str] = []
    original_channel = ResourceChannel.__init__

    def channel(self: ResourceChannel, case: Any) -> None:
        original_channel(self, case)
        engine = self.engine

        def capture(
            request: BrowserCaptureRequest, *, control: OperationControl
        ) -> BrowserCaptureResult:
            nonlocal stopped
            assert engine.last_readout is not None
            request.check_readout(b.spec.configuration.spec, engine.last_readout)
            page = Page(c["public"])
            page.url = c["public"].start_url
            result = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=datetime.now(timezone.utc),
                private_result=ShoppingCategoryPageCollector().collect(
                    page, request.collector_id, request.collector_version, control
                ),
            )
            capture_calls.append(request.collector_id)
            setattr(engine, "last_capture", result)
            stopped = fault == "cancel-after-capture"
            return result

        patch.setattr(engine, "last_capture", None, raising=False)
        patch.setattr(engine, "capture_page", capture, raising=False)

    patch.setattr(ResourceChannel, "__init__", channel)
    cap = CaptureAuthority(store)
    cap.denied = fault == "capture-denied"
    contexts = UnitNavigationContextAuthority()
    comparison = CategoryNavigationInitialComparison(store)
    original_compare = comparison.compare

    def compare(*args: Any, **kwargs: Any) -> Any:
        result = original_compare(*args, **kwargs)
        if fault == "comparison-denied":
            raise PermissionError("synthetic comparison admission")
        return result

    patch.setattr(comparison, "compare", compare)
    original_put = store.put

    def publish(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if (
            fault == "initial-write"
            and metadata.content_schema == "initial-state-checks/1"
        ):
            raise OSError("initial persistence failure")
        return EvidenceRef.model_validate(
            original_put(raw, metadata, control=control, exchange_id=exchange_id)
        )

    patch.setattr(store, "put", publish)

    class Control:
        def checkpoint(self) -> float:
            if stopped:
                raise OperationStopped("CANCELLED", "category-initial-caller")
            return float(b.controls.bind(base).checkpoint())

        def wait(self, seconds: float) -> None:
            self.checkpoint()
            b.controls.bind(base).wait(seconds)
            self.checkpoint()

    declaration_ref = put(store, d)
    admission_bodies: list[InitializationAdmissionInputs] = []

    class BodyAuthority(UnitInitializationAuthority):
        def verify_with_inputs(
            self,
            plan: TaskExecutionPlan,
            declaration: TaskInitializationPlan,
            inputs: InitializationAdmissionInputs,
            operation: OperationContext,
            control: OperationControl,
        ) -> None:
            inputs.require_original(plan, declaration_ref, declaration)
            admission_bodies.append(inputs)
            assert all(value is admission_bodies[0] for value in admission_bodies)
            super().verify(plan, declaration, operation, control)
            if fault == "final-admission-denied" and len(admission_bodies) == 5:
                raise PermissionError("Original current category admission revoked")

    initializer = shopping_category_task_initialization(
        plan,
        d,
        declaration_ref,
        owner,
        c["preparations"],
        BodyAuthority(),
        contexts,
        contexts,
        cap,
        UnitInitialAuthority(),
        comparison,
        store,
        b.controls,
    )
    try:
        if fault == "none":
            result = initializer.start(plan, operation("start"), Control())
            assert (
                initializer.state.phase == "initialized"
                and result.actor.schema_version == "actor-run-request/2"
            )
            assert (
                initializer.state.baseline is not None
                and initializer.state.baseline.status == "ready"
            )
            assert (
                initializer.state.equivalence is not None
                and initializer.state.equivalence.status == "equivalent"
            )
            assert result.actor.task == c["public"] and len(capture_calls) == 1
            saved["result"] = result
        else:
            with pytest.raises(TaskInitializationUnconfirmed) as failure:
                initializer.start(plan, operation("start"), Control())
            assert initializer.state.phase == "quarantined"
            saved["primary"] = type(failure.value.primary).__name__
        saved["body_admission_count"] = len(admission_bodies)
        with pytest.raises(DispatchAlreadyCommitted):
            initializer.start(plan, operation("start"), Control())
        assert len(b.channels) == 1 and b.channels[0].engine.calls == ["start"]
    finally:
        if owner.phase == "open":
            close = b.op.cleanup(
                "category-initializer-close",
                now=datetime.now(timezone.utc),
                seconds=30,
            )
            owner.close(close, b.controls.bind(close))
    assert owner.closed is not None and owner.closed.state == "closed"
    ending = json.loads(
        store.read(owner.closed.events[-1].evidence[0], control=guard())
    )
    saved.update(
        closed=True,
        capture_calls=len(capture_calls),
        source_attempt=source_attempt,
        candidate_attempt=scope.attempt_id,
    )
    return ClosureReceipt.model_validate_json(json.dumps(ending["details"]["closure"]))


def initialization_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, original: Any, fault: str
) -> dict[str, Any]:
    saved: dict[str, Any] = {}

    def bound(c: dict[str, Any]) -> ClosureReceipt:
        b, owner, store, scope = (
            c["browser_case"],
            c["browser_owner"],
            c["store"],
            c["scope"],
        )
        assert owner.phase == "new" and not b.channels
        historical_scope = scope.model_copy(
            update={
                "attempt_id": "historical-category",
                "context_id": "historical-context",
            }
        )
        historical = source(
            baseline(
                node / "historical-native",
                store,
                (original[0], None, c["public"]),
                scope_override=historical_scope,
            ),
            store,
            scoped=True,
        )
        missing = []
        for ref in dict.fromkeys(evidence_references(historical)):
            try:
                store.read(ref, control=guard())
            except EvidenceNotFound:
                missing.append((ref.content_schema, ref.sha256))
        assert not missing, (
            "Historical unit graph must be completely durable before initialization",
            missing,
        )
        source_operation = historical.baseline.operation.model_copy(
            update={
                "operation_id": "historical-context-freeze",
                "attempt_id": None,
                "allocation_id": None,
                "recovery_ref": None,
            }
        )
        source_receipt = assemble_public_context(historical, source_operation)
        context_ref = put(store, source_receipt)
        env = EnvironmentBaseline.model_validate_json(
            store.read(c["environment_ref"], control=guard())
        )
        snapshot = c["worker"].snapshot
        assert snapshot is not None
        base = c["prepare"].operation.model_copy(
            update={
                "operation_id": "category-task",
                "allocation_id": None,
                "recovery_ref": None,
            }
        )
        declaration = SiteTaskPreparationPlan(
            scope=scope,
            site_spec_ref=put(store, c["c"].spec),
            task_binding_ref=c["prepare"].binding_ref,
            private_input_ref=store.put(
                c["prepare"].private_input.encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="shopping-category-execution-input/1",
                    visibility="private",
                    producer="unit",
                ),
                control=guard(),
            ),
            snapshot_schema="shopping-category-recovery/1",
            snapshot_operation=snapshot.request.operation,
            prepare_operation=c["prepare"].operation,
            environment_operation=env.operation,
            resource_read_operation=env.operation.cleanup(
                "category-resource-read", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"attempt_id": None}),
        )
        prep_ref = put(store, declaration)
        run = RunBinding(
            owner=scope.owner,
            plan_ref=reference(
                {"synthetic_upstream_run": True}, "run-plan/1", store=store
            ),
            release_ref=b.spec.configuration.installation.manifest_ref,
            submission_key="category-unit",
        )
        attempt = AttemptBinding(
            run=run,
            attempt_id=scope.attempt_id,
            task=scope.task,
            claim_ref=reference(
                {"synthetic_upstream_claim": True},
                "execution-task-claim/1",
                store=store,
            ),
        )
        skill = turn().skill
        skill_ref = put(store, skill, "public")
        execution_inputs = ExecutionTaskInputs(
            task_binding_ref=c["prepare"].binding_ref,
            source_context_receipt_ref=context_ref,
            skill_ref=skill_ref,
            attempt_id=scope.attempt_id,
        )
        parameters = reference(
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
                    configuration_ref=parameters,
                    context_window=65536,
                    output_reserve=4096,
                    input_limit=61440,
                    soft_target=24576,
                ),
            ),
        )
        intent = TaskAttemptIntent(
            schema_version="execution-task-intent/1",
            binding=attempt,
            skill_digest=skill.content_digest,
            public_context_ref=source_receipt.public_context_ref,
            execution_policy_ref=put(
                store,
                EngineeringActorPolicy(
                    skill=skill,
                    memory=InactivePolicy(
                        status="disabled", reason="unit initializer only"
                    ),
                    max_generations=1,
                    max_interactions=1,
                    actor_projection=FullAxProjection(),
                    actor_context_ref=put(store, context),
                    candidate_id="category-unit",
                    revision_round=0,
                ),
            ),
            execution_inputs_ref=put(store, execution_inputs),
        )
        plan = TaskExecutionPlan(
            schema_version="task-execution-plan/2",
            intent=intent,
            reset_plan_ref=c["plan_ref"],
            declaration_ref=prep_ref,
            skill_ref=skill_ref,
            evaluation=EvaluationContract(
                identity=scope.task,
                attempt_id=scope.attempt_id,
                task_contract_ref=c["prepare"].binding_ref,
                public_task_ref=c["binding"].public_task_ref,
                completion_spec_ref=c["binding"].private_spec_ref,
                requirements=REQUIREMENTS,
                scope="engineering",
            ),
            operation=base,
            read_operation=base.model_copy(
                update={"operation_id": "category-task-read", "attempt_id": None}
            ),
            cleanup_seconds=30,
            source_ref=put(
                store,
                ExecutionTaskSource(
                    run=run,
                    task=c["binding"],
                    intent=intent,
                    source_context_receipt_ref=context_ref,
                ),
            ),
        )
        record = c["c"].journal.read(c["c"].spec.token, c["c"].op)
        acquired = SiteTaskAcquired(
            scope=scope,
            declaration_ref=prep_ref,
            operation=base.model_copy(
                update={"operation_id": base.operation_id + ".acquiring"}
            ),
            site_started_ref=put(store, c["live"].site),
            resource_intent_ref=record.events[1].evidence[0],
            resource_acquired_ref=record.events[2].evidence[0],
        )
        prepared = SiteTaskPrepared(
            scope=scope,
            declaration_ref=prep_ref,
            acquired_ref=put(store, acquired),
            snapshot_request_ref=put(store, snapshot.request),
            snapshot_result_ref=put(store, c["snapshot_result"]),
            snapshot_ref=c["prepare"].snapshot_ref,
            environment_selection_ref=c["environment_selection_ref"],
            environment_ref=c["environment_ref"],
            publication=c["publication"],
        )
        saved["prepared_constructor"] = prepared
        return initialize_current(
            c,
            patch,
            fault,
            saved,
            plan,
            put(store, prepared),
            context_ref,
            parameters,
            put(store, context),
            historical_scope.attempt_id,
        )

    prepared_family_case(
        root,
        node,
        patch,
        "none",
        category=(original[0], original[2]),
        retain_browser=True,
        on_bound=bound,
    )
    return saved
