"""Shared Actor loop and registered browser; explicit one-response synthetic model."""

import hashlib
from pathlib import Path
from typing import Protocol
from lab_generate_skill.domain.state_scope import StateScope
from site_resource_fixtures import Case as SiteResourceCase
from collections.abc import Callable
from lab_generate_skill.ports.actor_context import ActorInputPreparation
from lab_generate_skill.application.actor_loop import ActorLoopDeps, RecordedActorRunner
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.evidence import EvidenceRef
from map_initial_records_fixtures import InitialCase
from browser_resource_fixtures import ResourceCase
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from map_registered_worker_fixtures import RegisteredMapCase
from actor_loop_fixtures import UnitAuthority, RunAuthority
from test_evidence_run_plans import persisted_plan, frozen_binding
from test_actor_protocol import turn
from state_contract_fixtures import allocation, recovery
from preparation_record_fixtures import put
from retrieval_fixtures import reference


class BrowserActorCase(Protocol):
    @property
    def resource(self) -> SiteResourceCase: ...
    @property
    def scope(self) -> StateScope: ...
    @property
    def workspace(self) -> Path: ...
    @property
    def binding(self) -> EvidenceRef: ...


def execute_actor(
    c: RegisteredMapCase, i: InitialCase, *, terminal: bool = False
) -> tuple[EvidenceRef, EvidenceRef, InteractionTrace, TraceSnapshot]:
    return execute_browser_actor(c, i.browser.resource, i.session, terminal=terminal)


def execute_browser_actor(
    c: BrowserActorCase,
    b: ResourceCase,
    session: EvidenceBrowserSession,
    *,
    terminal: bool = False,
    request: ActorRunRequest | None = None,
    binding: AttemptBinding | None = None,
    context_factory: (
        Callable[[ActorRunRequest, FileTraceJournal], ActorInputPreparation] | None
    ) = None,
    on_journal: Callable[[FileTraceJournal], None] | None = None,
) -> tuple[EvidenceRef, EvidenceRef, InteractionTrace, TraceSnapshot]:
    store = c.resource.evidence
    given = request
    if (given is None) != (binding is None):
        raise ValueError("Original supplied request and attempt binding must be paired")
    assert session.observation_ref is not None
    op = b.op.model_copy(update={"operation_id": "map-shared-actor"})
    original_run = persisted_plan(store)
    run = RunPlan.model_validate(
        original_run.model_copy(
            update={
                "tasks": (
                    original_run.tasks[0].model_copy(update={"identity": c.scope.task}),
                ),
                "resources": original_run.resources.model_copy(
                    update={
                        "max_actor_generations_per_attempt": 1,
                        "max_interactions_per_attempt": 1,
                    }
                ),
            }
        )
    )
    bound = frozen_binding(store, run).model_copy(update={"owner": c.scope.owner})
    if binding is not None:
        bound = binding.run
    plan = TracePlan(
        binding=(
            binding
            if binding is not None
            else AttemptBinding(
                run=bound,
                task=c.scope.task,
                attempt_id=c.scope.attempt_id,
                claim_ref=reference({"synthetic_trace_permission": True}, store=store),
            )
        ),
        scope=c.scope,
        initial_observation_ref=session.observation_ref,
        max_generations=1,
        max_interactions=1,
        capacity=TraceCapacity(
            max_events=32,
            max_bytes=1024 * 1024,
            max_event_bytes=32768,
            max_trace_bytes=1024 * 1024,
        ),
    )
    if given is not None:
        op = given.operation
    root = c.workspace / "map-actor-journal"
    root.mkdir()
    journal = FileTraceJournal(root, plan, b.controls, store, UnitAuthority())
    journal.create(plan, op.model_copy(update={"operation_id": "map-trace-create"}))
    public = turn()
    task_binding = TaskBinding.model_validate_json(store.read(c.binding))
    model_recovery = recovery(False).model_copy(
        update={"owner": c.scope.owner, "baseline_ref": task_binding.baseline_ref}
    )
    model_token = allocation("actor", attempt=False).model_copy(
        update={"owner": c.scope.owner, "recovery_ref": put(store, model_recovery)}
    )
    request = (
        given
        if given is not None
        else ActorRunRequest(
            scope=c.scope,
            task=b.spec.configuration.spec.task,
            skill=public.skill,
            memory=public.memory,
            initial_observation_ref=session.observation_ref,
            model_allocation=model_token,
            browser_allocation=b.spec.token,
            parameters_refs=(
                reference(
                    {"fixture": "one synthetic response"},
                    "model-parameters/1",
                    store=store,
                ),
            ),
            operation=op,
            generation_seconds=30,
            interaction_seconds=30,
            cleanup_seconds=30,
        )
    )

    class Model:
        def validate(
            self, intent: GenerationIntent, *, control: OperationControl
        ) -> None:
            ActorPrompt.model_validate_json(store.read(intent.input_ref, control))

        def generate(
            self, intent: GenerationIntent, *, control: OperationControl
        ) -> ActorGeneration:
            assert journal.read(op).project().intent == intent
            prompt = ActorPrompt.model_validate_json(
                store.read(intent.input_ref, control)
            )
            completion = ActorTextCompletion(
                generation_id=intent.generation_id,
                request_id=intent.request_id,
                input_ref=intent.input_ref,
                model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
                parameters_ref=intent.parameters_ref,
                text=(
                    '{"action":"send_msg_to_user(\'done\')"}'
                    if terminal
                    else '{"action":"click(\'a\')"}'
                ),
                finish_reason="stop",
            )
            return ActorGeneration.model_validate(
                {
                    **intent.model_dump(exclude={"schema_version"}),
                    "schema_version": (
                        "actor-generation/2"
                        if intent.context_preparation_ref is not None
                        else "actor-generation/1"
                    ),
                    "status": "completed",
                    "response_ref": put(store, completion),
                    "failure_ref": None,
                }
            )

    if on_journal is not None:
        on_journal(journal)
    context = None if context_factory is None else context_factory(request, journal)
    runner = RecordedActorRunner(
        ActorLoopDeps(
            journal,
            store,
            EvidenceObservations(store, b.controls),
            Model(),
            session,
            RecordedActorDecisions(store, b.controls),
            prepare_actor,
            RunAuthority(),
            b.controls,
            b.clock,
            context=context,
        )
    )
    snapshot = runner.run(request)
    assert journal.read(op) == snapshot
    trace = snapshot.project().sealed
    assert trace is not None and trace.generations == trace.interactions == 1
    return put(store, trace), put(store, snapshot), trace, snapshot
