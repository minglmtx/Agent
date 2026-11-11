"""Actual CAS/journal/role components with explicit synthetic model/browser authority."""

import hashlib
from dataclasses import dataclass
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
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_events import GenerationIntent, TraceProgressEvent
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_control_fixtures import EvidenceFixtureStore
from trace_journal_fixtures import fixture as trace_fixture
from state_contract_fixtures import allocation, recovery
from retrieval_fixtures import reference
from test_run_journal import command
from test_actor_protocol import turn


class UnitAuthority:
    denied = False

    def verify_plan(self, plan: TracePlan, op: OperationContext) -> None:
        assert plan.scope.attempt_id == op.attempt_id

    def verify_event(
        self, snapshot: TraceSnapshot, event: TraceProgressEvent, op: OperationContext
    ) -> None:
        assert event.operation.run_id == snapshot.plan.scope.owner.run_id

    def verify(
        self,
        trace: InteractionTrace,
        observations: tuple[ResolvedObservation, ...],
        op: OperationContext,
    ) -> None:
        assert observations[0].record.sequence == 0
        assert all(o.record.task == trace.scope.task for o in observations)


class RunAuthority:
    denied = False
    calls = 0

    def verify(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        self.calls += 1
        if self.denied:
            raise PermissionError("unit live authority denied")
        assert snapshot.plan.scope == request.scope
        control.checkpoint()


class Model:
    def __init__(
        self,
        store: EvidenceFixtureStore,
        journal: FileTraceJournal,
        responses: tuple[str, ...],
    ) -> None:
        self.store, self.journal, self.responses = store, journal, responses
        self.calls = 0
        self.failure: BaseException | None = None
        self.status = "completed"
        self.prompts: list[ActorPrompt] = []

    def validate(self, intent: GenerationIntent, *, control: OperationControl) -> None:
        ActorPrompt.model_validate_json(self.store.read(intent.input_ref, control))

    def generate(
        self, intent: GenerationIntent, *, control: OperationControl
    ) -> ActorGeneration:
        snapshot = self.journal.read(command(attempt="attempt"))
        assert snapshot.project().intent == intent
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        prompt = ActorPrompt.model_validate_json(
            self.store.read(intent.input_ref, control)
        )
        self.prompts.append(prompt)
        response_ref = failure_ref = None
        if self.status == "completed":
            completion = ActorTextCompletion(
                generation_id=intent.generation_id,
                request_id=intent.request_id,
                input_ref=intent.input_ref,
                model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
                parameters_ref=intent.parameters_ref,
                text=self.responses[min(self.calls - 1, len(self.responses) - 1)],
                finish_reason="stop",
            )
            response_ref = reference(
                completion, "actor-model-response/1", store=self.store
            )
        else:
            failure_ref = reference(
                {"actual_attempted_status": self.status},
                "generation-failure/1",
                store=self.store,
            )
        return ActorGeneration.model_validate(
            {
                **intent.model_dump(exclude={"schema_version"}),
                "schema_version": (
                    "actor-generation/2"
                    if intent.schema_version == "actor-generation-intent/2"
                    else "actor-generation/1"
                ),
                "status": self.status,
                "response_ref": response_ref,
                "failure_ref": failure_ref,
            }
        )


class Browser:
    def __init__(self, store: EvidenceFixtureStore, journal: FileTraceJournal) -> None:
        self.store, self.journal = store, journal
        self.calls = 0
        self.failure: BaseException | None = None

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult:
        snapshot = self.journal.read(command(attempt="attempt"))
        view = snapshot.project()
        assert view.action is not None and view.action.decision.action == action
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        before = view.current_observation(snapshot.plan)
        old = Observation.model_validate_json(self.store.read(before, control))
        observed = old.model_copy(
            update={
                "observation_id": "after-" + str(self.calls),
                "sequence": old.sequence + 1,
                "text": "[2] button Save\nSaved public state",
            }
        )
        after = reference(observed, "observation/1", "public", self.store)
        terminal = action.name == "send_msg_to_user"
        raw = reference(
            {
                "action_id": action.action_id,
                "observation_ref": after.model_dump(mode="json"),
                "terminal": terminal,
            },
            "browser-step-return/1",
            store=self.store,
        )
        return StepResult(
            scope=snapshot.plan.scope,
            operation=operation,
            action_id=action.action_id,
            before_observation_ref=before,
            observation_ref=after,
            return_ref=raw,
            terminal=terminal,
        )


@dataclass
class LoopCase:
    store: EvidenceFixtureStore
    journal: FileTraceJournal
    request: ActorRunRequest
    model: Model
    browser: Browser
    authority: RunAuthority
    runner: RecordedActorRunner


def case(
    root: Path,
    responses: tuple[str, ...] = (
        '{"action":"click(\'2\')"}',
        '{"action":"send_msg_to_user(\'Saved\')"}',
    ),
) -> LoopCase:
    data = trace_fixture(root, outcomes=("returned",))
    controls = data.journal().controls
    journal = FileTraceJournal(
        root / "journal", data.plan, controls, data.store, UnitAuthority()
    )
    journal.create(data.plan, command("create-loop", attempt="attempt"))
    model, browser, authority = (
        Model(data.store, journal, responses),
        Browser(data.store, journal),
        RunAuthority(),
    )
    for attempt in (False, True):
        reference(recovery(attempt), "recovery-plan/1", store=data.store)
    public = turn()
    request = ActorRunRequest(
        scope=data.plan.scope,
        task=public.task,
        skill=public.skill,
        memory=public.memory,
        initial_observation_ref=data.plan.initial_observation_ref,
        model_allocation=allocation("actor", attempt=False),
        browser_allocation=allocation("browser"),
        parameters_refs=(data.data.trace.turns[0].generation.parameters_ref,)
        * data.plan.max_generations,
        operation=command("run-actor", attempt="attempt"),
        generation_seconds=10,
        interaction_seconds=10,
        cleanup_seconds=15,
    )
    deps = ActorLoopDeps(
        journal,
        data.store,
        EvidenceObservations(data.store, controls),
        model,
        browser,
        RecordedActorDecisions(data.store, controls),
        prepare_actor,
        authority,
        controls,
        SystemClock(),
    )
    return LoopCase(
        data.store,
        journal,
        request,
        model,
        browser,
        authority,
        RecordedActorRunner(deps),
    )
