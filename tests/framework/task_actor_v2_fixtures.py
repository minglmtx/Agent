"""File task admission and shared v2 service/once; synthetic physical rights.

Owner/role data is declared before publication. Test injection only constructs
isolated fixture data; no frozen records or runtime authority are patched.
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.local_actor_evidence import ActorEvidence
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.bootstrap.actor_context_runtime import freeze_actor_context
from lab_generate_skill.bootstrap.task_actor import (
    CurrentTaskActorBinding,
    TaskActorResources,
)
from lab_generate_skill.application.task_actor_admission import TaskActorAdmissionDeps
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.identity import Site
from source_actor_context_fixtures import source_context_case
from source_actor_trace import SourceTraceAuthority
from task_execution_fixtures import task_case, TaskCase, UnitBrowser
from construction_storage_fixtures import put
import construction_storage_fixtures as construction_data
import state_contract_fixtures as states
import actor_admission_fixtures as admission_data
from test_run_journal import command
from test_evidence_run_plans import persisted_plan


class UnitCurrentSourceAuthority:
    def __init__(self, task: TaskCase) -> None:
        self.task = task
        self.denied = False
        self.calls = 0
        self.callback: Any = None

    def verify(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.denied:
            raise OwnershipConflict("Synthetic current physical source denied")
        assert request == self.task.phases.initialized.actor
        assert snapshot.plan.binding == self.task.plan.intent.binding
        if self.callback is not None:
            self.callback()


class NativeUnitBrowser:
    def __init__(self, original: UnitBrowser, task: TaskCase) -> None:
        self.original, self.task = original, task

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult:
        result = self.original.step(action, operation, control=control)
        observed = Observation.model_validate_json(
            self.task.admission.data.store.read(result.observation_ref)
        )
        raw = BrowserReadout(
            scope=result.scope,
            operation=operation,
            action=action,
            observation=observed,
            events=(),
            environment_reward=0.0,
            terminated=False,
            truncated=False,
            protocol_terminal=True,
        )
        return StepResult.model_validate(
            result.model_copy(
                update={
                    "return_ref": put(
                        self.task.admission.data.store, raw, "browser-step-return/1"
                    )
                }
            )
        )


@dataclass
class CurrentTaskCase:
    task: TaskCase
    native: Any
    completed: list[LocalActorExecution]
    source: UnitCurrentSourceAuthority
    binding: CurrentTaskActorBinding
    resources: TaskActorResources


def current_task_case(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    site: Site = "map",
    shared_native: Any = None,
    task_builder: Callable[[Path], TaskCase] | None = None,
    recorded_teacher: bool = False,
) -> CurrentTaskCase:
    root.mkdir()
    native = (
        source_context_case(root / "original-engine", monkeypatch)
        if shared_native is None
        else shared_native
    )
    original_plan = persisted_plan
    original_scope = states.scope

    def site_fixture(
        path: Path, *, allowed_actions: tuple[str, ...]
    ) -> construction_data.StorageFixture:
        return construction_data.fixture(
            path,
            site=site,
            allowed_actions=allowed_actions,
            recorded_teacher=recorded_teacher,
        )

    def declared_scope() -> Any:
        return original_scope().model_copy(
            update={"owner": native.scope.binding.resource.owner}
        )

    def configured_plan(store: Any) -> RunPlan:
        seen: set[str] = set()

        def copy_reference(reference: EvidenceRef) -> None:
            if reference.sha256 in seen:
                return
            seen.add(reference.sha256)
            raw = native.actor.evidence.read(reference)
            metadata = EvidenceMetadata.model_validate(
                reference.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            )
            assert store.put(raw, metadata) == reference

        for reference in [
            native.scope.binding.release_ref,
            native.scope.binding.model_binding_ref,
            native.scope.binding.spec_ref,
            native.scope.binding.acquired_ref,
            native.scope.binding.resource.recovery_ref,
            native.policy.software_evidence_ref,
        ]:
            copy_reference(reference)
        model = ActorModelBinding.model_validate_json(
            store.read(native.scope.binding.model_binding_ref)
        )
        copy_reference(model.engine_config_ref)
        params_ref = put(store, native.params, "model-parameters/1")
        model = ActorModelBinding.model_validate_json(
            store.read(native.scope.binding.model_binding_ref)
        )
        run = original_plan(store)
        return RunPlan.model_validate(
            run.model_copy(
                update={
                    "release_ref": native.scope.binding.release_ref,
                    "models": tuple(
                        (
                            role.model_copy(
                                update={
                                    "provider": "fixed-actor-worker",
                                    "model": model.model,
                                    "model_binding_ref": native.scope.binding.model_binding_ref,
                                    "parameters_ref": params_ref,
                                }
                            )
                            if role.role == "actor"
                            else role
                        )
                        for role in run.models
                    ),
                }
            )
        )

    with pytest.MonkeyPatch.context() as declarations:
        declarations.setattr(states, "scope", declared_scope)
        declarations.setattr(construction_data, "persisted_plan", configured_plan)
        declarations.setattr(admission_data, "construction_fixture", site_fixture)
        task = (task_case if task_builder is None else task_builder)(
            root / "original-task"
        )
    store = task.admission.data.store
    plans = EvidenceRunPlans(store, task.deps.controls)
    run = plans.load(task.plan.intent.binding.run, task.plan.read_operation)
    actor = next(role for role in run.models if role.role == "actor")
    old = task.phases.initialized.actor
    count = len(old.parameters_refs)
    context = freeze_actor_context(
        native.scope.spec,
        (actor.parameters_ref,) * count,
        native.policy,
        store,
        soft_target=24576,
        control=task.deps.controls.bind(task.plan.operation),
    )
    request = ActorRunRequest.model_validate(
        {
            **old.model_dump(),
            "schema_version": "actor-run-request/2",
            "candidate_id": "original-candidate-"
            + str(task.plan.intent.candidate_slot),
            "revision_round": max(0, task.plan.intent.candidate_slot - 3),
            "context_configuration_ref": put(
                store, context, "actor-context-configuration/1"
            ),
            "model_allocation": native.scope.binding.resource,
            "parameters_refs": (actor.parameters_ref,) * count,
            "generation_seconds": 120,
        }
    )
    task.phases.initialized = task.phases.initialized.model_copy(
        update={"actor": request}
    )
    completed: list[LocalActorExecution] = []
    old_journal = task.actor.runner.deps.journal
    trace_plan = old_journal.read(command(attempt=request.scope.attempt_id)).plan
    trace_root = root / "v2-task-trace"
    trace_root.mkdir()
    journal = FileTraceJournal(
        trace_root,
        trace_plan,
        task.deps.controls,
        store,
        SourceTraceAuthority(trace_plan, store, task.deps.controls, completed),
    )
    journal.create(
        trace_plan,
        command(
            "current-task-trace-create"
            + ("-" + request.scope.attempt_id if shared_native is not None else ""),
            attempt=request.scope.attempt_id,
        ),
    )
    browser = UnitBrowser(task.phases, journal)
    task.browser = browser
    calls = root / "original-task-calls"
    calls.mkdir()
    scope = copy.copy(native.scope)
    scope.evidence = ActorEvidence(store)
    resources = TaskActorResources(
        cast(ActorExecutionScope, scope),
        NativeUnitBrowser(browser, task),
        journal,
        calls,
        completed,
    )
    source = UnitCurrentSourceAuthority(task)
    admission = TaskActorAdmissionDeps(
        task.deps.construction,
        task.deps.runs,
        task.deps.admission.claims,
        plans,
        store,
        source,
    )
    binding = CurrentTaskActorBinding(
        task.plan,
        admission,
        lambda initial, prepared: resources,
        store,
        task.deps.controls,
        task.deps.clock,
    )
    task.deps = replace(task.deps, actors=binding)
    return CurrentTaskCase(task, native, completed, source, binding, resources)
