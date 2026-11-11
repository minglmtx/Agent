"""Engineering trace on the actual acquired Actor; no formal task admission."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_execution_authority import (
    ResourceLocalActorAuthority,
)
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.domain.local_actor import LocalActorCall, LocalActorExecution
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorPublicTurn
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.domain.trace_events import GenerationIntent, GenerationPlanned
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_resource_fixtures import ResourceCase
from actor_loop_fixtures import UnitAuthority
from test_evidence_run_plans import persisted_plan, frozen_binding
from retrieval_fixtures import reference


class EngineeringCallAuthority:
    def __init__(
        self,
        journal: FileTraceJournal,
        intent: GenerationIntent,
        prompt: ActorPrompt,
        params: LocalActorParameters,
        read_op: OperationContext,
    ) -> None:
        self.journal, self.intent, self.prompt, self.params, self.read_op = (
            journal,
            intent,
            prompt,
            params,
            read_op,
        )
        self.denied = False
        self.completed: list[LocalActorExecution] = []

    def verify(
        self,
        call: LocalActorCall,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        guard: ProcessOwnerGuard,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("engineering source not admitted")
        if (
            call.intent != self.intent
            or prompt != self.prompt
            or parameters != self.params
        ):
            raise OwnershipConflict("engineering original public call differs")
        pending = self.journal.read(self.read_op).project().intent
        if (phase == "preflight" and pending is not None) or (
            phase == "dispatch" and pending != call.intent
        ):
            raise OwnershipConflict("engineering original trace phase differs")

    def verify_return(
        self, execution: LocalActorExecution, control: OperationControl
    ) -> None:
        control.checkpoint()
        if execution.call.intent != self.intent:
            raise OwnershipConflict("engineering return belongs to another call")
        self.completed.append(execution)


@dataclass
class RegisteredCall:
    journal: FileTraceJournal
    model: RecordedLocalActorModel
    business: EngineeringCallAuthority
    authority: ResourceLocalActorAuthority
    dispatch: ActorDispatch
    read_op: OperationContext


def registered_call(
    c: ResourceCase,
    scope: ActorExecutionScope,
    root: Path,
    public: ActorPublicTurn,
    params: LocalActorParameters,
) -> RegisteredCall:
    root.mkdir()
    (root / "trace").mkdir()
    (root / "calls").mkdir()
    task = public.observation.record.task
    state = StateScope(
        owner=c.spec.token.owner,
        task=task,
        attempt_id=public.observation.record.attempt_id,
        context_id=public.observation.record.context_id,
    )
    run = persisted_plan(c.evidence)
    run = RunPlan.model_validate(
        run.model_copy(
            update={"tasks": (run.tasks[0].model_copy(update={"identity": task}),)}
        )
    )
    bound = frozen_binding(c.evidence, run).model_copy(update={"owner": state.owner})
    observed = reference(
        public.observation.record, "observation/1", "public", c.evidence
    )
    plan = TracePlan(
        binding=AttemptBinding(
            run=bound,
            task=task,
            attempt_id=state.attempt_id,
            claim_ref=reference({"engineering_trace": True}, store=c.evidence),
        ),
        scope=state,
        initial_observation_ref=observed,
        max_generations=run.resources.max_actor_generations_per_attempt,
        max_interactions=run.resources.max_interactions_per_attempt,
        capacity=TraceCapacity(
            max_events=128,
            max_bytes=1024 * 1024,
            max_event_bytes=32768,
            max_trace_bytes=1024 * 1024,
        ),
    )

    def op(name: str) -> OperationContext:
        return OperationContext(
            operation_id=name,
            run_id=state.owner.run_id,
            owner_id=state.owner.owner_id,
            attempt_id=state.attempt_id,
            deadline=c.op.deadline,
        )

    journal = FileTraceJournal(
        root / "trace", plan, c.controls, c.evidence, UnitAuthority()
    )
    journal.create(plan, op("engineering-trace-create"))
    prompt = prepare_actor(public)
    intent = GenerationIntent(
        scope=state,
        operation=op("engineering-generate").model_copy(
            update={
                "allocation_id": c.spec.token.allocation_id,
                "recovery_ref": c.spec.token.recovery_ref,
            }
        ),
        generation_id="generation",
        request_id="engineering-request",
        before_observation_ref=observed,
        input_ref=reference(prompt, "actor-model-input/1", store=c.evidence),
        parameters_ref=reference(params, "model-parameters/1", store=c.evidence),
    )
    read_op = op("engineering-trace-read")
    business = EngineeringCallAuthority(journal, intent, prompt, params, read_op)
    authority = ResourceLocalActorAuthority(scope, business)
    model = RecordedLocalActorModel(
        root / "calls", scope.binding, scope.engine, c.evidence, c.controls, authority
    )
    dispatch = ActorDispatch(
        intent=GenerationPlanned(
            operation=op("engineering-plan-generation"), intent=intent
        ),
        expected_revision=0,
        result_operation=intent.operation.cleanup(
            "engineering-result-cleanup", now=c.op.deadline, seconds=15
        ),
    )
    return RegisteredCall(journal, model, business, authority, dispatch, read_op)
