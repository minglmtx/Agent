"""Pure write-ahead state projection; pending intents are never runnable reads."""

from dataclasses import dataclass, field
from .actor_generation import ActorGeneration
from .errors import InvalidTransition, OwnershipConflict
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .trace import InteractionTrace, TraceTurn, observation_progress_from_turns
from .trace_events import (
    ActionPlanned,
    DecisionRejected,
    GenerationIntent,
    GenerationObserved,
    GenerationPlanned,
    InteractionObserved,
    TraceProgressEvent,
    TraceSealed,
    ReadPlanned,
    ReadObserved,
)
from .trace_plan import TracePlan


def check_trace_operation(
    plan: TracePlan, op: OperationContext, *, execute: bool = False
) -> None:
    scope = plan.scope
    if (op.run_id, op.owner_id, op.attempt_id) != (
        scope.owner.run_id,
        scope.owner.owner_id,
        scope.attempt_id,
    ) or (execute and op.mode != "execute"):
        raise OwnershipConflict(
            "Trace command requires the original attempt and allowed phase"
        )


@dataclass
class TraceProjection:
    """Internal fold state, freshly derived; never a persisted service container."""

    turns: list[TraceTurn] = field(default_factory=list)
    intent: GenerationIntent | None = None
    generation: ActorGeneration | None = None
    action: ActionPlanned | None = None
    reading: ReadPlanned | None = None
    sealed: InteractionTrace | None = None
    halted: bool = False
    generation_ids: set[str] = field(default_factory=set)
    request_ids: set[str] = field(default_factory=set)
    action_ids: set[str] = field(default_factory=set)
    read_ids: set[str] = field(default_factory=set)
    operation_ids: set[str] = field(default_factory=set)

    @property
    def reserve(self) -> int:
        if self.sealed is not None:
            return 0
        if self.action is not None or self.reading is not None:
            return 2
        if self.generation is not None:
            return 3
        if self.intent is not None:
            return 4
        return 1

    def current_observation(self, plan: TracePlan) -> EvidenceRef:
        for turn in reversed(self.turns):
            if turn.interaction is not None and turn.interaction.result is not None:
                return turn.interaction.result.observation_ref
        return plan.initial_observation_ref

    @property
    def interactions(self) -> int:
        return sum(
            t.interaction is not None
            and t.interaction.outcome in ("returned", "returned_incomplete")
            for t in self.turns
        )

    def _operation(
        self, plan: TracePlan, op: OperationContext, *, execute: bool = False
    ) -> None:
        check_trace_operation(plan, op, execute=execute)
        if op.operation_id in self.operation_ids:
            raise OwnershipConflict("Trace operation identity was already used")
        self.operation_ids.add(op.operation_id)

    def advance(self, plan: TracePlan, event: TraceProgressEvent) -> None:
        if self.sealed is not None:
            raise InvalidTransition("Trace is already sealed")
        self._operation(
            plan,
            event.operation,
            execute=isinstance(event, (GenerationPlanned, ActionPlanned, ReadPlanned)),
        )
        if isinstance(event, GenerationPlanned):
            if (
                self.intent is not None
                or self.halted
                or len(self.turns) >= plan.max_generations
                or self.interactions >= plan.max_interactions
            ):
                raise InvalidTransition("Trace cannot start another generation")
            intent = event.intent
            if (
                intent.scope != plan.scope
                or intent.before_observation_ref != self.current_observation(plan)
            ):
                raise OwnershipConflict(
                    "Generation intent changed original scope or observation"
                )
            if (
                intent.generation_id in self.generation_ids
                or intent.request_id in self.request_ids
            ):
                raise OwnershipConflict("Generation/request identity cannot be reused")
            self._operation(plan, intent.operation, execute=True)
            self.generation_ids.add(intent.generation_id)
            self.request_ids.add(intent.request_id)
            self.intent = intent
        elif isinstance(event, GenerationObserved):
            if self.intent is None or self.generation is not None:
                raise InvalidTransition("No unmatched generation intent")
            if not self.intent.matches(event.generation):
                raise OwnershipConflict(
                    "Observed generation changed its original dispatch"
                )
            if event.generation.status == "completed":
                self.generation = event.generation
            else:
                self.turns.append(TraceTurn(generation=event.generation))
                self.intent = None
                self.halted = True
        elif isinstance(event, DecisionRejected):
            if (
                self.generation is None
                or self.action is not None
                or self.reading is not None
            ):
                raise InvalidTransition("No response awaiting decision")
            if (
                event.decision.outcome != "invalid"
                or event.decision.generation_id != self.generation.generation_id
            ):
                raise OwnershipConflict(
                    "Decision rejection changed original generation"
                )
            self.turns.append(
                TraceTurn(generation=self.generation, decision=event.decision)
            )
            self.generation = None
            self.intent = None
        elif isinstance(event, ActionPlanned):
            if (
                self.generation is None
                or self.action is not None
                or self.reading is not None
            ):
                raise InvalidTransition("No response awaiting action")
            decision = event.decision
            if (
                decision.outcome != "action"
                or decision.action is None
                or decision.generation_id != self.generation.generation_id
            ):
                raise OwnershipConflict("Action plan changed original decision")
            if decision.action.action_id in self.action_ids:
                raise OwnershipConflict("Action identity cannot be reused")
            self._operation(plan, event.execution_operation, execute=True)
            self.action_ids.add(decision.action.action_id)
            self.action = event
        elif isinstance(event, ReadPlanned):
            if (
                self.generation is None
                or self.action is not None
                or self.reading is not None
            ):
                raise InvalidTransition(
                    "No response awaiting an original readonly decision"
                )
            decision = event.decision
            request = decision.read_request
            if (
                request is None
                or decision.read_policy is None
                or decision.generation_id != self.generation.generation_id
            ):
                raise OwnershipConflict(
                    "Read intent changed original generation/decision"
                )
            if (
                request.snapshot.scope != plan.scope
                or request.snapshot.observation_ref != self.current_observation(plan)
            ):
                raise OwnershipConflict(
                    "Read intent changed current public observation/scope"
                )
            if request.request_id in self.read_ids:
                raise OwnershipConflict("Read request identity cannot be reused")
            progress = observation_progress_from_turns(
                tuple(self.turns),
                request.snapshot,
                decision.read_policy,
                initial_displayed_spans=decision.displayed_source_spans,
                initial_progress_fingerprint=decision.active_progress_fingerprint,
            )
            expected_active = progress.active
            if decision.active_read_ref != (
                None if expected_active is None else expected_active.result_ref
            ):
                raise OwnershipConflict(
                    "Previous returned reading was not included in the actual next model input"
                )
            if expected_active is not None and (
                decision.displayed_source_spans,
                decision.active_progress_fingerprint,
            ) != (
                expected_active.displayed_spans,
                expected_active.progress_fingerprint,
            ):
                raise OwnershipConflict(
                    "Actual next reading input changed original active-window geometry"
                )
            self._operation(plan, event.execution_operation, execute=True)
            self.read_ids.add(request.request_id)
            self.reading = event
        elif isinstance(event, ReadObserved):
            if self.reading is None or self.generation is None:
                raise InvalidTransition("No original read intent awaiting outcome")
            reading = event.reading
            if reading.operation != self.reading.execution_operation:
                raise OwnershipConflict("Reading changed original execution operation")
            turn = TraceTurn(
                schema_version="trace-turn/2",
                generation=self.generation,
                decision=self.reading.decision,
                reading=reading,
            )
            if reading.outcome == "returned":
                policy = self.reading.decision.read_policy
                assert policy is not None
                progress = observation_progress_from_turns(
                    tuple((*self.turns, turn)), reading.request.snapshot, policy
                )
                self.halted = progress.controlled_stop is not None
            else:
                self.halted = True
            self.turns.append(turn)
            self.intent = None
            self.generation = None
            self.reading = None
        elif isinstance(event, InteractionObserved):
            if self.action is None or self.generation is None:
                raise InvalidTransition("No unmatched action intent")
            interaction = event.interaction
            if interaction.operation != self.action.execution_operation:
                raise OwnershipConflict("Interaction changed original action operation")
            turn = TraceTurn(
                generation=self.generation,
                decision=self.action.decision,
                interaction=interaction,
            )
            self.turns.append(turn)
            self.halted = interaction.outcome in (
                "uncertain",
                "returned_incomplete",
            ) or (interaction.result is not None and interaction.result.terminal)
            self.intent = None
            self.generation = None
            self.action = None
        else:
            if (
                self.action is not None
                or self.reading is not None
                or (self.intent is not None and self.generation is None)
            ):
                raise InvalidTransition(
                    "Unknown pending dispatch needs its original outcome before sealing"
                )
            turns = tuple(self.turns)
            if self.generation is not None:
                turns += (TraceTurn(generation=self.generation),)
            self.sealed = InteractionTrace(
                scope=plan.scope,
                operation=event.operation,
                initial_observation_ref=plan.initial_observation_ref,
                max_generations=plan.max_generations,
                max_interactions=plan.max_interactions,
                turns=turns,
                stop_reason=event.stop_reason,
                stop_evidence_ref=event.stop_evidence_ref,
            )
