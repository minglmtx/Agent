"""Current Actor/2 and original record producers; native/kernel/model/DOM are doubles."""

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RoleModelPlan,
    RunResources,
    ExecutionWorkload,
)
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.optional_policies import RunPolicies, InactivePolicy
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.bootstrap.shopping_category_evaluation import (
    shopping_category_evaluator,
)
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from lab_generate_skill.sites.shopping.evidence_schema import (
    PageCaptureEvidence,
    SiteCaptureEvidence,
)
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from lab_generate_skill.evaluators.shopping.navigation import REQUIREMENTS
from shopping_prepared_family_fixtures import prepared_family_case
from shopping_category_browser_fixtures import Page
from task_capture_actor_fixtures import controlled_context
from map_actor_trace_fixtures import execute_browser_actor
from test_evidence_run_plans import frozen_binding
from context_budget_fixtures import profile
from actor_context_projection_fixtures import actor_projection_case
from retrieval_fixtures import reference
from preparation_record_fixtures import put
from test_actor_protocol import turn
from state_contract_fixtures import allocation, recovery
from test_slurm_commands import guard


def complete_case(
    root: Path,
    node: Path,
    patch: pytest.MonkeyPatch,
    original: tuple[bytes, PublicTask],
    consume: Callable[[dict[str, Any]], None],
    *,
    heading: str = "Electronics",
    on_current_initial: Callable[[dict[str, Any]], None] | None = None,
    on_current_capture: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    if (on_current_initial is None) != (on_current_capture is None):
        raise ValueError(
            "Original initial producer and capture consumer must be paired"
        )
    captured: dict[str, Any] = {}

    def ready(c: dict[str, Any]) -> None:
        store, b, session = c["store"], c["browser_case"], c["session"]
        scope, binding = c["scope"], c["binding"]
        model_ref = reference(
            {"synthetic_model_only": True}, "model-binding/1", store=store
        )
        params_ref = reference(
            {
                "synthetic_parameters_only": True,
                "max_input_tokens": 61440,
                "max_new_tokens": 4096,
            },
            "model-parameters/1",
            store=store,
        )
        context = ActorContextConfiguration(
            policy=actor_projection_case("shopping").policy,
            profiles=(
                profile(
                    provider="fixed-actor-worker",
                    routing_ref=model_ref,
                    configuration_ref=params_ref,
                    context_window=65536,
                    output_reserve=4096,
                    input_limit=61440,
                    soft_target=24576,
                ),
            ),
        )
        context_ref = put(store, context)
        public_turn = turn()
        policy = EngineeringActorPolicy(
            skill=public_turn.skill,
            memory=public_turn.memory,
            max_generations=1,
            max_interactions=1,
            actor_projection=FullAxProjection(),
            actor_context_ref=context_ref,
            candidate_id="category-unit",
            revision_round=0,
        )
        policy_ref = put(store, policy)
        inputs = ExecutionTaskInputs(
            task_binding_ref=c["prepare"].binding_ref,
            source_context_receipt_ref=reference(
                {"unit_source_permission_only": True},
                "public-context-receipt/1",
                store=store,
            ),
            skill_ref=reference(
                policy.skill, "compact-skill/1", visibility="public", store=store
            ),
            attempt_id=scope.attempt_id,
        )
        installation = b.spec.configuration.installation
        release = installation.manifest
        raw = release.model_dump_json().encode()
        manifest_ref = installation.manifest_ref
        observed = store.put(
            raw,
            EvidenceMetadata(
                media_type=manifest_ref.media_type,
                content_schema=manifest_ref.content_schema,
                visibility=manifest_ref.visibility,
                producer=manifest_ref.producer,
            ),
            control=guard(),
        )
        assert observed == manifest_ref
        run = RunPlan(
            run_id=scope.owner.run_id,
            release_ref=installation.manifest_ref,
            purpose="engineering",
            split="train",
            split_manifest_ref=reference({"unit_split": "train"}, store=store),
            task_manifest_ref=reference(
                {"unit_task": binding.identity.task_id}, store=store
            ),
            tasks=(binding,),
            workload=ExecutionWorkload(
                execution_policy_ref=policy_ref,
                task_inputs_ref=put(store, inputs),
                seed=0,
            ),
            policies=RunPolicies(
                actor_memory=policy.memory,
                teacher_template=InactivePolicy(
                    status="not_applicable", reason="Actor-only unit engineering"
                ),
            ),
            models=(
                RoleModelPlan(
                    role="actor",
                    provider="fixed-actor-worker",
                    model="unit-model",
                    model_binding_ref=model_ref,
                    parameters_ref=params_ref,
                    paid=False,
                ),
            ),
            resources=RunResources(
                configuration_ref=reference({"unit_resources": True}, store=store),
                max_parallel_tasks=1,
                max_actor_generations_per_attempt=1,
                max_interactions_per_attempt=1,
                operation_timeout_seconds=60,
                cleanup_timeout_seconds=30,
            ),
            run_capacity=JournalCapacity(
                max_attempts=1, max_entries=64, max_bytes=1024**2, max_entry_bytes=32768
            ),
            budget=None,
        )
        bound = frozen_binding(store, run).model_copy(update={"owner": scope.owner})
        attempt = AttemptBinding(
            run=bound,
            task=scope.task,
            attempt_id=scope.attempt_id,
            claim_ref=reference(
                {"unit_trace_permission_only": True}, "source-claim/1", store=store
            ),
        )
        model_recovery = recovery(False).model_copy(
            update={"owner": scope.owner, "baseline_ref": binding.baseline_ref}
        )
        model = allocation("actor", attempt=False).model_copy(
            update={"owner": scope.owner, "recovery_ref": put(store, model_recovery)}
        )
        actor = ActorRunRequest(
            schema_version="actor-run-request/2",
            scope=scope,
            task=c["public"],
            skill=policy.skill,
            memory=policy.memory,
            initial_observation_ref=session.observation_ref,
            model_allocation=model,
            browser_allocation=b.spec.token,
            context_configuration_ref=context_ref,
            candidate_id=policy.candidate_id,
            revision_round=0,
            parameters_refs=(params_ref,),
            operation=b.op.model_copy(
                update={
                    "operation_id": "category-original-actor",
                    **(
                        {"allocation_id": None, "recovery_ref": None}
                        if on_current_capture is not None
                        else {}
                    ),
                }
            ),
            generation_seconds=30,
            interaction_seconds=30,
            cleanup_seconds=30,
        )
        if on_current_initial is not None:
            on_current_initial(
                dict(
                    c,
                    actor=actor,
                    attempt=attempt,
                    run=run,
                    policy=policy,
                    execution_inputs=inputs,
                )
            )
        engine = b.channels[0].engine
        value = engine.value
        endpoint = c["live"].site.instance.endpoint.rstrip("/") + "/electronics.html"

        def next_value(
            operation: OperationContext, action: BrowserAction | None
        ) -> BrowserReadout:
            old = value(operation, action)
            observed = old.observation.model_copy(
                update={
                    "tabs": tuple(
                        t.model_copy(update={"url": endpoint})
                        for t in old.observation.tabs
                    )
                }
            )
            current = BrowserReadout.model_validate(
                {**old.model_dump(), "observation": observed}
            )
            engine.last_readout = current
            return current

        patch.setattr(engine, "value", next_value)
        resource = SimpleNamespace(
            resource=c["c"],
            scope=scope,
            workspace=root,
            binding=c["prepare"].binding_ref,
        )
        journals: list[Any] = []
        trace_ref, journal_ref, trace, journal = execute_browser_actor(
            resource,
            b,
            session,
            request=actor,
            binding=attempt,
            context_factory=lambda r, j: controlled_context(r, j, store),
            on_journal=journals.append,
        )
        assert trace.generations == 1 and journal.project().sealed == trace
        assert all(
            t.generation.schema_version == "actor-generation/2" for t in trace.turns
        )
        event = trace.turns[-1].interaction
        assert event is not None and event.result is not None
        returned = BrowserReadout.model_validate_json(
            store.read(event.result.return_ref, guard())
        )
        page = Page(c["public"])
        page.url = endpoint
        page.health.update(url=endpoint, title="Electronics")

        def dom(program: str) -> dict[str, Any]:
            assert "heading_texts" in program
            return {
                "schema_version": "shopping-category-navigation-page/1",
                "health": page.health,
                "heading_texts": [heading] if heading else [],
                "document_ready": "complete",
            }

        patch.setattr(page, "evaluate", dom)
        from test_browser_capture import Authority as PageAuthority

        def capture_page(
            request: BrowserCaptureRequest, *, control: OperationControl
        ) -> BrowserCaptureResult:
            request.check_readout(b.spec.configuration.spec, returned)
            result = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=datetime.now(timezone.utc),
                private_result=ShoppingCategoryPageCollector().collect(
                    page, request.collector_id, request.collector_version, control
                ),
            )
            engine.last_capture = result
            return result

        patch.setattr(engine, "last_capture", None, raising=False)
        patch.setattr(engine, "capture_page", capture_page, raising=False)
        if on_current_capture is not None:
            assert len(journals) == 1
            on_current_capture(
                dict(
                    c,
                    actor=actor,
                    attempt=attempt,
                    run=run,
                    policy=policy,
                    execution_inputs=inputs,
                    trace_ref=trace_ref,
                    journal_ref=journal_ref,
                    trace=trace,
                    journal=journal,
                    trace_journal=journals[0],
                )
            )
            return
        request = BrowserCaptureRequest(
            scope=scope,
            operation=b.op.model_copy(update={"operation_id": "category-final-page"}),
            observation_sha256=hashlib.sha256(
                returned.observation.model_dump_json().encode()
            ).hexdigest(),
            collector_id="shopping-category-navigation-page",
            collector_version="1",
        )
        capture = RecordedBrowserCapture(session.engine, store, PageAuthority(store))
        result_ref = capture.capture(request, control=guard())
        assert capture.intent_ref is not None
        captured.update(
            trace_ref=trace_ref,
            journal_ref=journal_ref,
            trace=trace,
            journal=journal,
            returned_ref=event.result.return_ref,
            page=PageCaptureEvidence(
                intent_ref=capture.intent_ref, result_ref=result_ref
            ),
        )

    def closed(c: dict[str, Any]) -> None:
        if on_current_capture is not None:
            assert c["browser_owner"].phase == "closed"
            return
        store, site, closure = c["store"], c["c"], c["closure"]
        assert (
            c["browser_case"]
            .journal.read(c["browser_case"].spec.token, c["browser_case"].op)
            .state
            == "closed"
        )

        class NativeAuthority:
            def verify_capture(
                self,
                configuration: Any,
                request: SiteCaptureRequest,
                intent_ref: EvidenceRef,
                control: OperationControl,
            ) -> None:
                intent = SiteCaptureIntent.model_validate_json(
                    store.read(intent_ref, control)
                )
                assert (
                    intent.request == request
                    and request.operation.parent_operation_id == closure.operation_id
                )
                assert site.journal.read(site.spec.token, site.op).state == "acquired"

        from lab_generate_skill.sites.shopping.tasks.navigation_lifecycle import (
            CategoryNavigationLifecycle,
        )

        worker: CategoryNavigationLifecycle = c["worker"]
        assert isinstance(worker, CategoryNavigationLifecycle)

        class NativeParent:
            configuration = site.spec.configuration

            def capture_task(
                self,
                request: SiteCaptureRequest,
                intent_ref: EvidenceRef,
                authority: Any,
                *,
                control: OperationControl,
            ) -> SiteTaskResult:
                authority.verify_capture(
                    self.configuration, request, intent_ref, control
                )
                return worker.capture_task(request, control=control)

        inspection = c["prepare"].model_copy(
            update={
                "action": "inspect",
                "operation": c["prepare"].operation.model_copy(
                    update={
                        "operation_id": "category-final-native-guard",
                        "parent_operation_id": closure.operation_id,
                    }
                ),
            }
        )
        request = SiteCaptureRequest(
            inspection=inspection,
            collector_id="shopping-category-navigation",
            collector_version="1",
        )
        capture = RecordedSiteCapture(NativeParent(), store, NativeAuthority())
        result = capture.capture(request, control=guard())
        assert capture.intent_ref is not None
        selected = CategoryNavigationEvidence(
            environment_ref=c["environment_selection_ref"],
            initial=c["initial_selection"],
            initial_checks_ref=c["initial_checks_ref"],
            trace_ref=captured["trace_ref"],
            trace_snapshot_ref=captured["journal_ref"],
            terminal_return_ref=captured["returned_ref"],
            page=captured["page"],
            final_guard=SiteCaptureEvidence(
                intent_ref=capture.intent_ref, result_ref=result
            ),
            browser_closure_ref=put(store, closure),
        )
        contract = EvaluationContract(
            identity=c["scope"].task,
            attempt_id=c["scope"].attempt_id,
            task_contract_ref=c["prepare"].binding_ref,
            public_task_ref=c["binding"].public_task_ref,
            completion_spec_ref=c["binding"].private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )

        def evaluator(selection: CategoryNavigationEvidence = selected) -> Any:
            return shopping_category_evaluator(
                selection,
                c["preparations"],
                site.spec,
                c["live"].site,
                c["prepare"].operation,
            )

        consume(
            dict(
                c, selected=selected, contract=contract, evaluator=evaluator, **captured
            )
        )

    prepared_family_case(
        root,
        node,
        patch,
        "none",
        category=original,
        on_ready=ready,
        on_closed=closed,
        retain_browser=on_current_capture is not None,
    )
