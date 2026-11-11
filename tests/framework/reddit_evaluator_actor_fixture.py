"""Recorded Actor loop with explicit synthetic model/browser, no live permission."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from lab_generate_skill.application.actor_loop import ActorLoopDeps, RecordedActorRunner
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.execution import RunBinding, AttemptBinding
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from test_evidence_run_plans import persisted_plan
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from evidence_control_fixtures import EvidenceFixtureStore
from actor_loop_fixtures import UnitAuthority, RunAuthority
from observation_fixtures import sample_observation
from reddit_preparation_fixtures import put, metadata
from test_actor_protocol import turn
from test_resource_journal import NoCancellation
from test_slurm_commands import guard


def recorded_trace(
    root: Path,
    store: EvidenceFixtureStore,
    browser: BrowserResourceSpec,
    operation: OperationContext,
    *,
    issued_title: bool = True,
) -> TraceSnapshot:
    task, scope = browser.configuration.spec.task, browser.configuration.spec.scope
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())

    def public(observed: Observation) -> EvidenceRef:
        return store.put(
            observed.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="observation/1",
                visibility="public",
                producer="explicit-synthetic-reddit-loop",
            ),
            guard(),
        )

    initial = sample_observation(task.identity, scope.context_id, scope.attempt_id)
    initial = initial.model_copy(
        update={
            "captured_at": datetime.now(timezone.utc),
            "tabs": tuple(
                t.model_copy(update={"url": task.start_url}) for t in initial.tabs
            ),
            "text": "[2] button Save native image",
        }
    )
    initial_ref = public(initial)
    synthetic = store.put(
        b'{"explicitly_synthetic":true}', metadata("unit-authority/1"), guard()
    )
    template = persisted_plan(store)
    run = RunPlan.model_validate(
        template.model_copy(
            update={
                "run_id": scope.owner.run_id,
                "purpose": "engineering",
                "tasks": (
                    template.tasks[0].model_copy(update={"identity": task.identity}),
                ),
                "workload": ExecutionWorkload(
                    execution_policy_ref=synthetic, task_inputs_ref=synthetic, seed=42
                ),
                "models": (template.models[0],),
                "budget": None,
                "run_capacity": template.run_capacity.model_copy(
                    update={"max_attempts": 1}
                ),
                "resources": template.resources.model_copy(
                    update={
                        "max_actor_generations_per_attempt": 2,
                        "max_interactions_per_attempt": 2,
                    }
                ),
            }
        )
    )
    plan = TracePlan(
        binding=AttemptBinding(
            run=RunBinding(
                owner=scope.owner,
                plan_ref=put(store, run),
                release_ref=run.release_ref,
                submission_key="unit-reddit",
            ),
            task=task.identity,
            attempt_id=scope.attempt_id,
            claim_ref=synthetic,
        ),
        scope=scope,
        initial_observation_ref=initial_ref,
        max_generations=2,
        max_interactions=2,
        capacity=TraceCapacity(
            max_events=32,
            max_bytes=524288,
            max_event_bytes=8192,
            max_trace_bytes=524288,
        ),
    )
    root.mkdir(mode=0o700)
    journal = FileTraceJournal(root, plan, controls, store, UnitAuthority())
    journal.create(
        plan, operation.model_copy(update={"operation_id": "create-reddit-trace"})
    )
    params = store.put(
        b'{"explicitly_synthetic":true}', metadata("model-parameters/1"), guard()
    )
    selected = turn()
    request = ActorRunRequest(
        scope=scope,
        task=task,
        skill=selected.skill,
        memory=selected.memory,
        initial_observation_ref=initial_ref,
        model_allocation=browser.token.model_copy(
            update={
                "allocation_id": "unit-model",
                "resource_kind": "actor",
                "scope": "batch",
                "attempt_id": None,
            }
        ),
        browser_allocation=browser.token,
        parameters_refs=(params, params),
        operation=operation.model_copy(
            update={
                "operation_id": "run-reddit-loop",
                "allocation_id": None,
                "recovery_ref": None,
            }
        ),
        generation_seconds=10,
        interaction_seconds=10,
        cleanup_seconds=15,
    )

    class Model:
        calls = 0

        def validate(
            self, intent: GenerationIntent, *, control: OperationControl
        ) -> None:
            ActorPrompt.model_validate_json(store.read(intent.input_ref, control))

        def generate(
            self, intent: GenerationIntent, *, control: OperationControl
        ) -> ActorGeneration:
            self.calls += 1
            prompt = ActorPrompt.model_validate_json(
                store.read(intent.input_ref, control)
            )
            response = ActorTextCompletion(
                generation_id=intent.generation_id,
                request_id=intent.request_id,
                input_ref=intent.input_ref,
                model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
                parameters_ref=intent.parameters_ref,
                text=(
                    '{"action":"click(\'2\')"}'
                    if self.calls == 1
                    else '{"action":"send_msg_to_user(\'Done\')"}'
                ),
                finish_reason="stop",
            )
            return ActorGeneration.model_validate(
                {
                    **intent.model_dump(exclude={"schema_version"}),
                    "status": "completed",
                    "response_ref": put(store, response),
                    "failure_ref": None,
                }
            )

    class Browser:
        calls = 0

        def step(
            self,
            action: BrowserAction,
            operation: OperationContext,
            *,
            control: OperationControl,
        ) -> StepResult:
            snapshot = journal.read(operation)
            before = snapshot.project().current_observation(snapshot.plan)
            old = Observation.model_validate_json(store.read(before, control))
            self.calls += 1
            observed = old.model_copy(
                update={
                    "observation_id": "unit-after-" + str(self.calls),
                    "sequence": old.sequence + 1,
                    "captured_at": datetime.now(timezone.utc),
                    "text": "[2] button Save\n"
                    + (
                        "Beautiful Sunset at the Beach"
                        if issued_title or self.calls == 2
                        else "No post title observed"
                    ),
                }
            )
            after = public(observed)
            terminal = action.name == "send_msg_to_user"
            returned = BrowserReadout(
                scope=scope,
                operation=operation,
                action=action,
                observation=observed,
                events=(),
                environment_reward=0.0,
                terminated=False,
                truncated=False,
                protocol_terminal=terminal,
            )
            return StepResult(
                scope=scope,
                operation=operation,
                action_id=action.action_id,
                before_observation_ref=before,
                observation_ref=after,
                return_ref=put(store, returned),
                terminal=terminal,
            )

    deps = ActorLoopDeps(
        journal,
        store,
        EvidenceObservations(store, controls),
        Model(),
        Browser(),
        RecordedActorDecisions(store, controls),
        prepare_actor,
        RunAuthority(),
        controls,
        clock,
    )
    return RecordedActorRunner(deps).run(request)
