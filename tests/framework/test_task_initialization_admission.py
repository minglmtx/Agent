"""Actual run/construction journals and stage outputs; physical rights explicit fake."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.construction_task_phases import (
    ConstructionTaskInitializationAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_preparation import SiteTaskPrepared
from lab_generate_skill.domain.initialization_admission_inputs import (
    InitializationAdmissionInputs,
)
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.ports.lifecycle import OperationControl
from construction_storage_fixtures import put
from task_execution_fixtures import task_case
from test_core_contracts import reference
from test_task_preparation_admission import declaration as preparation_declaration
from test_task_initialization_contracts import declaration as initialization_declaration


@pytest.mark.parametrize("body_mode", [False, True])
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "foreign-attempt",
        "changed-declaration",
        "missing-start-output",
        "source-denied",
        "changed-journal",
        "unlinked-cleanup",
        "changed-source-context",
    ],
)
def test_only_current_starting_attempt_and_its_original_preparation_can_initialize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, body_mode: bool
) -> None:
    c = task_case(tmp_path / "task")
    prep = preparation_declaration(c)
    c.plan = c.plan.model_copy(
        update={
            "declaration_ref": put(c.admission.data.store, prep, prep.schema_version)
        }
    )
    environment = reference("private", "environment-baseline/1")
    publication = PreparedPublication(
        selection=PreparationSelection(
            request_ref=reference("private", "site-task-request/2"),
            result_ref=reference("private", "site-task-result/1"),
            environment_ref=environment,
        ),
        preparation_ref=reference("private", "preparation-receipt/1"),
        prepared_ref=reference("private", "prepared-task/1"),
    )
    acquired = SiteTaskAcquired(
        scope=prep.scope,
        declaration_ref=c.plan.declaration_ref,
        operation=c.plan.operation.model_copy(
            update={"operation_id": c.plan.operation.operation_id + ".acquiring"}
        ),
        site_started_ref=reference("private", "site-resource-started/1"),
        resource_intent_ref=reference("private", "resource-acquisition-intent/1"),
        resource_acquired_ref=reference("private", "site-resource-fact/1"),
    )
    acquired_ref = put(c.admission.data.store, acquired, acquired.schema_version)
    prepared = SiteTaskPrepared(
        acquired_ref=acquired_ref,
        scope=prep.scope,
        declaration_ref=c.plan.declaration_ref,
        snapshot_request_ref=publication.selection.request_ref,
        snapshot_result_ref=publication.selection.result_ref,
        snapshot_ref=reference("private", "unit-snapshot/1"),
        environment_selection_ref=reference("private", "environment-selection/1"),
        environment_ref=environment,
        publication=publication,
    )
    prepared_ref = put(c.admission.data.store, prepared, prepared.schema_version)
    d = initialization_declaration()
    operations = (
        "browser_acquisition",
        "capture_operation",
        "initial_operation",
        "baseline_operation",
        "comparison_operation",
        "equivalence_operation",
    )
    changes: dict[str, Any] = {
        "scope": prep.scope,
        "prepared_result_ref": prepared_ref,
        "source_context_receipt_ref": c.admission.data.plan.context_receipt_ref,
        "actor": d.actor.model_copy(
            update={
                "model_allocation": d.actor.model_allocation.model_copy(
                    update={"owner": prep.scope.owner}
                )
            }
        ),
    }
    for name in operations:
        changes[name] = getattr(d, name).model_copy(
            update={
                "run_id": prep.scope.owner.run_id,
                "owner_id": prep.scope.owner.owner_id,
                "attempt_id": prep.scope.attempt_id,
            }
        )
    d = d.model_copy(update=changes)
    frozen = put(c.admission.data.store, d, d.schema_version)
    bridge = ConstructionTaskInitializationAuthority(
        frozen, c.deps.construction, c.deps.runs, c.phases, c.deps.evidence
    )
    store = c.admission.data.store
    inputs = InitializationAdmissionInputs(
        frozen,
        d,
        prepared,
        prep,
        acquired,
        TaskBinding.model_validate_json(store.read(prep.task_binding_ref)),
        ResetPlan.model_validate_json(store.read(c.plan.reset_plan_ref)),
    )

    def verify(
        plan: TaskExecutionPlan,
        declaration: Any,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        if body_mode:
            bridge.verify_with_inputs(plan, declaration, inputs, op, control)
        else:
            bridge.verify(plan, declaration, op, control)

    admitted = []

    class Preparation:
        def acquire(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> tuple[EvidenceRef, ...]:
            c.phases.acquire(plan, operation, control)
            return (acquired_ref,)

        def prepare(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> tuple[EvidenceRef, ...]:
            c.phases.prepare(plan, operation, control)
            return (prepared_ref,)

    class Initialization:
        def start(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> InitializedTask:
            wrong, declaration = operation, d
            if fault != "none":
                with monkeypatch.context() as patch:
                    expected: type[Exception] = OwnershipConflict
                    if fault == "foreign-attempt":
                        wrong = operation.model_copy(update={"attempt_id": "foreign"})
                    elif fault == "changed-declaration":
                        declaration = d.model_copy(
                            update={
                                "browser_spec_ref": d.browser_spec_ref.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        )
                    elif fault == "missing-start-output":
                        declaration = d.model_copy(
                            update={
                                "prepared_result_ref": put(
                                    c.admission.data.store,
                                    prepared.model_copy(
                                        update={
                                            "snapshot_ref": reference(
                                                "private", "other-snapshot/1"
                                            )
                                        }
                                    ),
                                    prepared.schema_version,
                                )
                            }
                        )
                        changed_frozen = put(
                            c.admission.data.store,
                            declaration,
                            declaration.schema_version,
                        )
                        patch.setattr(bridge, "declaration_ref", changed_frozen)
                    elif fault == "source-denied":
                        patch.setattr(c.phases, "denied", True)
                        expected = PermissionError
                    elif fault == "changed-source-context":
                        declaration = d.model_copy(
                            update={
                                "source_context_receipt_ref": d.source_context_receipt_ref.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        )
                        patch.setattr(
                            bridge,
                            "declaration_ref",
                            put(
                                c.admission.data.store,
                                declaration,
                                declaration.schema_version,
                            ),
                        )
                    elif fault == "unlinked-cleanup":
                        wrong = operation.cleanup(
                            "unlinked-read", now=c.deps.clock.utcnow(), seconds=10
                        )
                    else:
                        original = c.deps.runs.read
                        count = 0

                        def changed(op: OperationContext) -> Any:
                            nonlocal count
                            count += 1
                            snapshot = original(op)
                            if count == 2:
                                return snapshot.model_copy(
                                    update={
                                        "binding": snapshot.binding.model_copy(
                                            update={
                                                "submission_key": "foreign-revision"
                                            }
                                        )
                                    }
                                )
                            return snapshot

                        patch.setattr(c.deps.runs, "read", changed)
                        expected = RevisionConflict
                    with pytest.raises(expected):
                        verify(plan, declaration, wrong, control)
                assert c.model.calls == c.browser.calls == 0
            verify(plan, d, operation, control)
            admitted.append("starting")
            return c.phases.start(plan, operation, control)

    with pytest.raises(OwnershipConflict, match="live pending attempt"):
        verify(c.plan, d, c.plan.operation, c.deps.controls.bind(c.plan.operation))
    c.deps = replace(c.deps, preparation=Preparation(), initialization=Initialization())
    result = execute_task(c.plan, c.deps)
    assert result.evaluation.status == "failure" and admitted == ["starting"]
    assert c.model.calls == c.browser.calls == 1
    with pytest.raises(OwnershipConflict, match="starting"):
        bridge.verify(
            c.plan, d, c.plan.operation, c.deps.controls.bind(c.plan.operation)
        )
