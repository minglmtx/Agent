"""Original capture port with real local producers and explicit upstream premises.

Source/claim/model/kernel/DOM rights are doubles. Full source initialization is
not run: the upstream equivalence receipt is explicitly unknown, never positive.
The synthetic capture authority only grants this isolated port combination.
"""

from datetime import datetime, timezone
from typing import Any
from types import SimpleNamespace
from pathlib import Path
import json
import pytest
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.bootstrap.shopping_category_records import (
    category_initial_observations,
)
from lab_generate_skill.bootstrap.shopping_category_task_capture import (
    shopping_category_task_capture,
)
from lab_generate_skill.domain.baseline import InitialStateChecks, assemble_baseline
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceChecks,
    EquivalenceReceipt,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import EvaluationContract, CheckResult
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_capture import TaskCaptureInputs, TaskCapturePlan
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.adapters.sites.task_capture import TaskCaptureUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.evaluators.shopping.navigation import REQUIREMENTS
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from shopping_category_evaluation_fixtures import complete_case
from shopping_category_browser_fixtures import Page
from initial_observation_fixtures import Authority as InitialAuthority
from test_browser_capture import Authority as BrowserAuthority
from test_task_initialization_contracts import declaration
from task_capture_port_fixtures import UnitTaskCaptureAuthority
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from test_slurm_commands import guard


def capture_case(
    root: Path,
    node: Path,
    patch: pytest.MonkeyPatch,
    original: Any,
    *,
    heading: str,
    fault: str,
) -> dict[str, Any]:
    saved: dict[str, Any] = {}

    def initial(c: dict[str, Any]) -> None:
        b, store, session = c["browser_case"], c["store"], c["session"]
        start, actor = b.op, c["actor"]
        template = declaration()
        d = TaskInitializationPlan.model_validate(
            template.model_copy(
                update={
                    "scope": c["scope"],
                    "browser_spec_ref": c["initial_selection"].browser_spec_ref,
                    "browser_acquisition": start,
                    "actor": template.actor.model_copy(
                        update={
                            "model_allocation": actor.model_allocation,
                            "context_configuration_ref": actor.context_configuration_ref,
                            "parameters_refs": actor.parameters_refs,
                        }
                    ),
                    **{
                        name: start.model_copy(
                            update={
                                "operation_id": "category-port-"
                                + name.replace("_", "-")
                            }
                        )
                        for name in (
                            "capture_operation",
                            "initial_operation",
                            "baseline_operation",
                            "comparison_operation",
                            "equivalence_operation",
                        )
                    },
                }
            )
        )
        page, engine = Page(c["public"]), b.channels[0].engine
        page.url = c["public"].start_url

        def passive(
            request: BrowserCaptureRequest, *, control: OperationControl
        ) -> BrowserCaptureResult:
            request.check_readout(
                b.spec.configuration.spec, session.engine.last_readout
            )
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
        patch.setattr(engine, "capture_page", passive, raising=False)
        initial_rights = InitialAuthority(c["initial_selection"])

        def records(intent: EvidenceRef, result: EvidenceRef) -> Any:
            assert store.read(intent, guard()) and store.read(result, guard())
            return category_initial_observations(
                store, b.controls, c["preparations"], initial_rights
            )

        measurement = CapturedTaskInitialMeasurements(
            d,
            c["browser_owner"],
            store,
            b.controls,
            BrowserAuthority(store),
            records,
            collector_id="shopping-category-navigation-page",
            collector_version="1",
        )
        checked = measurement.record(c["initial_selection"], guard())
        assert (
            measurement.capture is not None
            and measurement.capture.intent_ref is not None
            and measurement.capture.result_ref is not None
        )
        fact = InitialStateChecks.model_validate_json(store.read(checked, guard()))
        baseline_inputs = c["baseline_inputs"].model_copy(
            update={"initial": fact, "initial_ref": checked}
        )
        baseline = assemble_baseline(baseline_inputs, d.baseline_operation)
        assert baseline.status == "ready"
        baseline_ref = put(store, baseline)
        # Honest upstream premise: this port does not implement or grant the
        # missing qualified cross-instance comparison. Never publish equivalent.
        unknown = EquivalenceChecks(
            scope=c["scope"],
            operation=d.comparison_operation,
            source_context_receipt_ref=c["execution_inputs"].source_context_receipt_ref,
            candidate_baseline_ref=baseline_ref,
            checks=StateChecks(
                required=c["spec"].equivalence_checks,
                checks=(
                    CheckResult(
                        name="shopping.initial.equivalence",
                        status="unknown",
                        reason_code="ISOLATED_UPSTREAM_PREMISE",
                        evidence=(baseline_ref,),
                    ),
                ),
            ),
        )
        equivalence = EquivalenceReceipt(
            scope=c["scope"],
            operation=d.equivalence_operation,
            source_context_receipt_ref=unknown.source_context_receipt_ref,
            candidate_baseline_ref=baseline_ref,
            checks_ref=put(store, unknown),
            status="unknown",
        )
        saved.update(
            declaration=d,
            initial_checks_ref=checked,
            initial_capture=measurement.capture,
            baseline_ref=baseline_ref,
            equivalence_ref=put(store, equivalence),
        )

    def collect(c: dict[str, Any]) -> None:
        b, store, owner, actor = (
            c["browser_case"],
            c["store"],
            c["browser_owner"],
            c["actor"],
        )
        intent = TaskAttemptIntent(
            schema_version="execution-task-intent/1",
            binding=c["attempt"],
            skill_digest=actor.skill.content_digest,
            public_context_ref=reference(
                {"isolated_upstream_public_context": True},
                "public-construction-context/1",
                visibility="public",
                store=store,
            ),
            execution_policy_ref=put(store, c["policy"]),
            execution_inputs_ref=put(store, c["execution_inputs"]),
        )
        source = ExecutionTaskSource(
            run=c["attempt"].run,
            task=c["binding"],
            intent=intent,
            source_context_receipt_ref=c["execution_inputs"].source_context_receipt_ref,
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
        plan = TaskExecutionPlan(
            schema_version="task-execution-plan/2",
            intent=intent,
            reset_plan_ref=c["plan_ref"],
            declaration_ref=put(store, saved["declaration"]),
            skill_ref=c["execution_inputs"].skill_ref,
            evaluation=contract,
            operation=actor.operation,
            read_operation=actor.operation.model_copy(
                update={"operation_id": "category-port-run-read", "attempt_id": None}
            ),
            cleanup_seconds=30,
            source_ref=put(store, source),
        )
        original_capture = saved["initial_capture"]
        inputs = TaskCaptureInputs(
            initialized=InitializedTask(
                baseline_ref=saved["baseline_ref"],
                equivalence_ref=saved["equivalence_ref"],
                actor=actor,
            ),
            initial=c["initial_selection"],
            initial_capture_intent_ref=original_capture.intent_ref,
            initial_capture_result_ref=original_capture.result_ref,
            initial_checks_ref=saved["initial_checks_ref"],
            environment_selection_ref=c["environment_selection_ref"],
            prepare_request_ref=c["publication"].selection.request_ref,
        )
        d = TaskCapturePlan(
            scope=c["scope"],
            requirements=REQUIREMENTS,
            page_operation_id="category-port-page",
            close_operation_id="category-port-close",
            guard_operation_id="category-port-guard",
            page_collector_id="shopping-category-navigation-page",
            page_collector_version="1",
            guard_collector_id="shopping-category-navigation",
            guard_collector_version="1",
            close_seconds=30,
        )

        class Authority(UnitTaskCaptureAuthority):
            def verify(
                self,
                plan: Any,
                declaration: Any,
                inputs: Any,
                snapshot: Any,
                operation: OperationContext,
                control: OperationControl,
            ) -> None:
                super().verify(plan, declaration, inputs, snapshot, operation, control)
                if (
                    fault == "close-denied"
                    and operation.operation_id == d.close_operation_id
                ):
                    raise PermissionError("Isolated category close permission denied")

        authority, browser_authority = Authority(), BrowserAuthority(store)
        authority.denied = fault == "task-denied"
        browser_authority.denied = fault == "page-denied"
        guards: list[SiteCaptureRequest] = []

        class NativeAuthority:
            def verify_capture(
                self,
                configuration: Any,
                request: SiteCaptureRequest,
                intent_ref: EvidenceRef,
                control: OperationControl,
            ) -> None:
                control.checkpoint()
                actual = SiteCaptureIntent.model_validate_json(
                    store.read(intent_ref, control)
                )
                assert (
                    configuration == c["c"].spec.configuration
                    and actual.request == request
                )
                assert owner.phase == "closed" and owner.closed is not None
                ending = json.loads(
                    store.read(owner.closed.events[-1].evidence[0], control)
                )
                closure = ClosureReceipt.model_validate_json(
                    json.dumps(ending["details"]["closure"])
                )
                assert closure.status == "closed" and closure.token == b.spec.token
                assert request.operation.parent_operation_id == closure.operation_id
                assert (
                    request.inspection.binding_ref == c["prepare"].binding_ref
                    and request.inspection.snapshot_ref == c["prepare"].snapshot_ref
                )
                if fault == "guard-denied":
                    raise PermissionError("Isolated category guard permission denied")

        class NativeParent:
            configuration = c["c"].spec.configuration

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
                guards.append(request)
                return SiteTaskResult.model_validate(
                    c["worker"].capture_task(request, control=control)
                )

        site = SimpleNamespace(
            site=c["live"].site,
            capture=NativeParent(),
            tasks=c["live"].tasks,
            resume=c["live"].resume,
        )
        capture, evaluator = shopping_category_task_capture(
            plan,
            d,
            put(store, d),
            lambda control: inputs,
            lambda: owner,
            lambda: c["trace_journal"],
            site,
            c["c"].spec,
            c["preparations"],
            authority,
            browser_authority,
            NativeAuthority(),
            store,
            b.controls,
            b.clock,
        )
        capture.preflight(plan, evaluator.requirements(contract), guard())
        original_put = store.put

        def publish(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
            *,
            exchange_id: str | None = None,
        ) -> EvidenceRef:
            if (
                fault == "page-write"
                and metadata.content_schema == "browser-capture-result/1"
            ) or (
                fault == "guard-write"
                and metadata.content_schema == "site-task-result/1"
            ):
                raise OSError("Isolated category capture write failure")
            if (
                metadata.content_schema == "shopping-category-navigation-evidence/1"
                and fault in ("terminal-write", "selection-write")
            ):
                selected = json.loads(raw)
                if (selected["final_guard"] is None) == (fault == "terminal-write"):
                    raise OSError("Isolated category selection write failure")
            return EvidenceRef.model_validate(
                original_put(raw, metadata, control, exchange_id=exchange_id)
            )

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "category-capture-fixture")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        operation = actor.operation.model_copy(
            update={"operation_id": "category-port-capture"}
        )
        with patch.context() as writes:
            writes.setattr(store, "put", publish)
            if fault == "none":
                result = capture.capture(plan, c["journal"], operation, guard())
                assert result.contract == contract and owner.phase == "closed"
                evaluated = evaluator.evaluate(contract, store, guard())
                assert evaluated.status == (
                    "success" if heading else "failure"
                ) and evaluated.reward == (1 if heading else 0)
                assert evaluator.evaluate(contract, store, guard()) == evaluated
            else:
                with pytest.raises(TaskCaptureUnconfirmed) as caught:
                    capture.capture(
                        plan,
                        c["journal"],
                        operation,
                        Cancel() if fault == "cancel" else guard(),
                    )
                assert (
                    capture.state.phase == "quarantined"
                    and caught.value.primary is not None
                )
                expected_type = (
                    OperationStopped
                    if fault == "cancel"
                    else OSError if fault.endswith("write") else PermissionError
                )
                assert isinstance(caught.value.primary, expected_type)
                expected_phase = (
                    "admission"
                    if fault in ("task-denied", "cancel")
                    else (
                        "browser-close"
                        if fault == "close-denied"
                        else (
                            "guard"
                            if fault
                            in ("guard-denied", "guard-write", "selection-write")
                            else "page"
                        )
                    )
                )
                assert caught.value.failed_phase == expected_phase
                if fault in ("guard-denied", "guard-write", "selection-write"):
                    assert (
                        owner.phase == "closed"
                        and capture.state.closure_ref is not None
                    )
                if fault in ("page-write", "terminal-write", "selection-write"):
                    assert caught.value.candidates
                with pytest.raises(OwnershipConflict):
                    evaluator.evaluate(contract, store, guard())
        with pytest.raises(DispatchAlreadyCommitted):
            capture.capture(plan, c["journal"], operation, guard())
        assert len(guards) == (
            1 if fault in ("none", "guard-write", "selection-write") else 0
        )
        saved.update(capture=capture, owner=owner, guards=guards)

    complete_case(
        root,
        node,
        patch,
        original,
        lambda c: None,
        heading=heading,
        on_current_initial=initial,
        on_current_capture=collect,
    )
    assert saved["owner"].phase == "closed"
    return saved
