"""Real current Actor2/journals; explicitly synthetic physical acquired premise.

This isolates metadata admission. The synthetic acquired document is not a
physical source grant; the original TaskExecutionAuthority remains mandatory.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.construction_task_phases import (
    ConstructionTaskCaptureAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.initial_observation import (
    BrowserAcquiredFact,
    InitialObservationSelection,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    TaskCaptureResult,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import resource_case
from retrieval_fixtures import reference
from task_actor_v2_fixtures import current_task_case
from task_execution_fixtures import task_case, TaskCase
from test_core_contracts import reference as shaped_ref


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "foreign-attempt",
        "changed-declaration",
        "actor-output",
        "baseline-output",
        "source-denied",
        "changed-journal",
    ],
)
@pytest.mark.parametrize("metadata_budget", [False, True], ids=["legacy", "metadata"])
def test_current_executing_actor_outputs_and_original_trace_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, metadata_budget: bool
) -> None:
    def declared_task(path: Path) -> TaskCase:
        task = task_case(path)
        binding = task.admission.data.plan.task
        ref = reference(binding, "task-binding/1", store=task.admission.data.store)
        task.plan = task.plan.model_copy(
            update={
                "evaluation": task.plan.evaluation.model_copy(
                    update={"task_contract_ref": ref}
                )
            }
        )
        return task

    current = current_task_case(
        tmp_path / "current", monkeypatch, task_builder=declared_task
    )
    c, request = current.task, current.task.phases.initialized.actor
    store = c.admission.data.store
    # Typed test-only startup details, independently closed. The metadata gate
    # receives a separately declared synthetic acquired premise, never rewrites
    # an original production receipt or reuses an ended worker.
    root = tmp_path / "unit-browser-template"
    root.mkdir()
    b = resource_case(root, monkeypatch)
    with registered_browser(
        b.spec,
        b.op,
        journal=b.journal,
        evidence=b.evidence,
        controls=b.controls,
        clock=b.clock,
        authority=b.authority,
    ) as browser:
        assert browser.resource_started_ref is not None
        template = BrowserAcquiredFact.model_validate_json(
            b.evidence.read(browser.resource_started_ref)
        )
    acquired = BrowserAcquiredFact(
        spec_sha256="f" * 64,
        token=request.browser_allocation,
        operation=c.plan.operation.model_copy(
            update={
                "operation_id": "unit-capture-acquired",
                "parent_operation_id": "unit-capture-acquisition",
            }
        ),
        state="acquired",
        details=template.details,
    )
    acquired_ref = reference(acquired, acquired.schema_version, store=store)
    publication = PreparedPublication(
        selection=PreparationSelection(
            request_ref=shaped_ref("private", "site-task-request/2"),
            result_ref=shaped_ref("private", "site-task-result/1"),
            environment_ref=shaped_ref("private", "environment-baseline/1"),
        ),
        preparation_ref=shaped_ref("private", "preparation-receipt/1"),
        prepared_ref=shaped_ref("private", "prepared-task/1"),
    )
    inputs = TaskCaptureInputs(
        initialized=c.phases.initialized,
        initial=InitialObservationSelection(
            preparation=publication,
            browser_spec_ref=shaped_ref("private", "browser-resource-spec/4"),
            browser_acquired_ref=acquired_ref,
        ),
        initial_capture_intent_ref=shaped_ref("private", "browser-capture-intent/1"),
        initial_capture_result_ref=shaped_ref("private", "browser-capture-result/1"),
        initial_checks_ref=shaped_ref("private", "initial-state-checks/1"),
        environment_selection_ref=shaped_ref("private", "environment-selection/1"),
        prepare_request_ref=publication.selection.request_ref,
    )
    declaration = TaskCapturePlan(
        scope=request.scope,
        requirements=c.plan.evaluation.requirements,
        page_operation_id="unit-page",
        close_operation_id="unit-close",
        guard_operation_id="unit-guard",
        page_collector_id="unit-page",
        page_collector_version="1",
        guard_collector_id="unit-guard",
        guard_collector_version="1",
        close_seconds=30,
    )
    if metadata_budget:
        declaration = TaskCapturePlan.model_validate(
            {
                **declaration.model_dump(),
                "schema_version": "task-capture-plan/2",
                "metadata_close_seconds": 30,
            }
        )
    frozen = reference(declaration, declaration.schema_version, store=store)
    bridge = ConstructionTaskCaptureAuthority(
        frozen,
        c.deps.construction,
        c.deps.runs,
        c.phases,
        lambda: current.resources.journal,
        store,
    )
    admitted = []

    class Capture:
        def preflight(
            self,
            plan: TaskExecutionPlan,
            requirements: EvidenceRequirements,
            control: OperationControl,
        ) -> None:
            c.phases.preflight(plan, requirements, control)

        def capture(
            self,
            plan: TaskExecutionPlan,
            snapshot: TraceSnapshot,
            operation: OperationContext,
            control: OperationControl,
        ) -> TaskCaptureResult:
            if fault != "none":
                with monkeypatch.context() as patch:
                    wrong, declared, selected = operation, declaration, inputs
                    expected: type[Exception] = OwnershipConflict
                    if fault == "foreign-attempt":
                        wrong = operation.model_copy(update={"attempt_id": "foreign"})
                    elif fault == "changed-declaration":
                        declared = declaration.model_copy(
                            update={"page_collector_version": "2"}
                        )
                    elif fault == "actor-output":
                        selected = inputs.model_copy(
                            update={
                                "initialized": inputs.initialized.model_copy(
                                    update={
                                        "actor": request.model_copy(
                                            update={"candidate_id": "foreign-candidate"}
                                        )
                                    }
                                )
                            }
                        )
                    elif fault == "baseline-output":
                        selected = inputs.model_copy(
                            update={
                                "initialized": inputs.initialized.model_copy(
                                    update={
                                        "baseline_ref": shaped_ref(
                                            "private", "baseline-receipt/1"
                                        )
                                    }
                                )
                            }
                        )
                    elif fault == "source-denied":
                        patch.setattr(c.phases, "denied", True)
                        expected = PermissionError
                    else:
                        original = c.deps.runs.read
                        count = 0

                        def changed(op: OperationContext) -> Any:
                            nonlocal count
                            count += 1
                            value = original(op)
                            return (
                                value
                                if count != 2
                                else value.model_copy(
                                    update={
                                        "binding": value.binding.model_copy(
                                            update={
                                                "submission_key": "changed-revision"
                                            }
                                        )
                                    }
                                )
                            )

                        patch.setattr(c.deps.runs, "read", changed)
                        expected = RevisionConflict
                    with pytest.raises(expected):
                        bridge.verify(
                            plan, declared, selected, snapshot, wrong, control
                        )
            bridge.verify(plan, declaration, inputs, snapshot, operation, control)
            admitted.append("executing")
            return c.phases.capture(plan, snapshot, operation, control)

    c.deps = replace(c.deps, capture=Capture())
    try:
        result = execute_task(c.plan, c.deps)
        assert result.evaluation.status == "failure" and admitted == ["executing"]
        assert c.browser.calls == current.native.loader.session.calls == 1
        with pytest.raises(OwnershipConflict):
            bridge.verify(
                c.plan,
                declaration,
                inputs,
                current.resources.journal.read(c.plan.operation),
                c.plan.operation,
                c.deps.controls.bind(c.plan.operation),
            )
    finally:
        current.native.client.close(c.deps.controls.bind(c.plan.operation))
