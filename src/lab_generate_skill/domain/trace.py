"""Ordered immutable interaction evidence; closure, judgment and permission separate.

Counters derive from actual records, never from generated action text. Pending or
uncertain work cannot be followed by a new turn. Reconcile original evidence in
an explicitly new version; never repeat the external call to fill a trace gap.
"""

from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .observation_read_fact import ObservationReadFact
from .observation_read import PublicObservationSnapshot, ObservationSourceSpan
from .observation_read_policy import ObservationReadPolicy
from .observation_read_progress import ObservationReadProgress
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .actor_generation import ActorGeneration, ActorDecision
from .browser import observation_reference
from .interaction import InteractionEvent
from .lifecycle import OperationContext
from .state_scope import StateScope, private_state_ref
from .validation import Contract


class TraceTurn(Contract):
    schema_version: Literal["trace-turn/1", "trace-turn/2"] = "trace-turn/1"
    generation: ActorGeneration
    decision: ActorDecision | None = None
    interaction: InteractionEvent | None = None
    reading: ObservationReadFact | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self, handler, self.schema_version == "trace-turn/1", ("reading",)
        )

    @model_validator(mode="after")
    def link_generation(self) -> Self:
        old = self.schema_version == "trace-turn/1"
        actor_version_fields(self, old, ("reading",), record_name="Trace turn")
        if old != (self.reading is None):
            raise ValueError(
                "Read trace turn requires explicit v2; original turns keep v1 bytes"
            )
        gen, event = self.generation, self.interaction
        decision = self.decision
        if gen.status == "completed":
            if decision is None:
                if event is not None or self.reading is not None:
                    raise ValueError("An interaction requires the parsed decision")
                return self
            if decision.generation_id != gen.generation_id:
                raise ValueError("Decision must belong to the completed generation")
            if decision.outcome == "read":
                reading = self.reading
                if (
                    reading is None
                    or event is not None
                    or decision.read_request is None
                ):
                    raise ValueError(
                        "Parsed read requires its actual read outcome, no browser interaction"
                    )
                if (reading.generation_id, reading.scope, reading.request) != (
                    gen.generation_id,
                    gen.scope,
                    decision.read_request,
                ):
                    raise OwnershipConflict(
                        "Read outcome changed original generation/scope/decision"
                    )
                if (
                    reading.request.snapshot.observation_ref
                    != gen.before_observation_ref
                ):
                    raise OwnershipConflict(
                        "Read did not consume the generation's current snapshot"
                    )
            elif self.reading is not None:
                raise ValueError(
                    "Only an actual read decision can supply a read outcome"
                )
            if (decision.outcome == "action") != (event is not None):
                raise ValueError(
                    "Selected action requires explicit dispatch/return/unknown facts"
                )
            if event is not None and decision.action != event.action:
                raise OwnershipConflict(
                    "Interaction action differs from parsed model response"
                )
        elif decision is not None or event is not None or self.reading is not None:
            raise ValueError(
                "Failed/uncertain generation cannot supply a decision or action"
            )
        if event is not None:
            if gen.status != "completed":
                raise ValueError("Only completed model responses can produce an action")
            if (event.scope, event.generation_id, event.before_observation_ref) != (
                gen.scope,
                gen.generation_id,
                gen.before_observation_ref,
            ):
                raise OwnershipConflict(
                    "Interaction must retain its generation and input observation"
                )
        return self


def observation_progress_from_turns(
    turns: tuple[TraceTurn, ...],
    snapshot: PublicObservationSnapshot,
    policy: ObservationReadPolicy,
    *,
    initial_displayed_spans: tuple[ObservationSourceSpan, ...] | None = None,
    initial_progress_fingerprint: str | None = None,
) -> ObservationReadProgress:
    """Derive metadata from original turns; never a second resumable ledger."""
    for turn in turns:
        if (
            turn.reading is not None
            and turn.reading.request.snapshot.observation_ref
            == snapshot.observation_ref
        ):
            assert turn.decision is not None
            initial_displayed_spans = turn.decision.displayed_source_spans
            initial_progress_fingerprint = turn.decision.active_progress_fingerprint
            break
    fields: dict[str, object] = {}
    if initial_displayed_spans is not None:
        fields.update(
            schema_version="observation-read-progress/2",
            initial_displayed_spans=initial_displayed_spans,
            initial_progress_fingerprint=initial_progress_fingerprint,
        )
    progress = ObservationReadProgress.model_validate(
        dict(snapshot=snapshot, policy=policy, records=(), no_progress=0) | fields
    )
    for turn in turns:
        reading = turn.reading
        if (
            reading is not None
            and reading.request.snapshot.observation_ref == snapshot.observation_ref
        ):
            if (
                turn.decision is None
                or turn.decision.read_policy != policy
                or reading.request.snapshot != snapshot
            ):
                raise OwnershipConflict(
                    "Same-observation reading changed its original policy/scope"
                )
            if reading.outcome == "returned":
                assert reading.result is not None
                progress = progress.returned(reading.result)
    return progress


class InteractionTrace(Contract):
    schema_version: Literal["interaction-trace/1"] = "interaction-trace/1"
    scope: StateScope
    operation: OperationContext
    initial_observation_ref: EvidenceRef
    max_generations: int = Field(ge=1, le=10000)
    max_interactions: int = Field(ge=1, le=10000)
    turns: tuple[TraceTurn, ...] = Field(max_length=10000)
    stop_reason: Literal[
        "finished",
        "generation_limit",
        "interaction_limit",
        "cancelled",
        "error",
        "uncertain",
    ]
    stop_evidence_ref: EvidenceRef

    @property
    def generations(self) -> int:
        return len(self.turns)

    @property
    def completed_generations(self) -> int:
        return sum(turn.generation.status == "completed" for turn in self.turns)

    @property
    def interactions(self) -> int:
        return sum(
            turn.interaction is not None
            and turn.interaction.outcome in ("returned", "returned_incomplete")
            for turn in self.turns
        )

    @property
    def uncertain_interactions(self) -> int:
        return sum(
            turn.interaction is not None and turn.interaction.outcome == "uncertain"
            for turn in self.turns
        )

    @property
    def final_observation_ref(self) -> EvidenceRef:
        for turn in reversed(self.turns):
            if turn.interaction is not None and turn.interaction.result is not None:
                return turn.interaction.result.observation_ref
        return self.initial_observation_ref

    @model_validator(mode="after")
    def ordered_original_facts(self) -> Self:
        observation_reference(self.initial_observation_ref)
        private_state_ref(self.stop_evidence_ref, "trace-stop/1")
        if (
            self.operation.run_id,
            self.operation.owner_id,
            self.operation.attempt_id,
        ) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            self.scope.attempt_id,
        ):
            raise OwnershipConflict("Trace publication must belong to its attempt")
        if (
            self.generations > self.max_generations
            or self.interactions > self.max_interactions
        ):
            raise ValueError("Trace exceeds frozen generation/interaction limits")
        current = self.initial_observation_ref
        operations = {self.operation.operation_id}
        generations: set[str] = set()
        requests: set[str] = set()
        actions: set[str] = set()
        uncertain = terminal = interrupted = False
        returned = 0
        for turn in self.turns:
            if (
                uncertain
                or terminal
                or interrupted
                or returned >= self.max_interactions
            ):
                raise ValueError(
                    "No new generation after uncertain, terminal or interaction limit"
                )
            gen, event = turn.generation, turn.interaction
            if gen.scope != self.scope or gen.before_observation_ref != current:
                raise OwnershipConflict(
                    "Trace generation must consume current observation in original scope"
                )
            if (
                gen.generation_id in generations
                or gen.request_id in requests
                or gen.operation.operation_id in operations
            ):
                raise ValueError(
                    "Generation, request and operation identities cannot repeat"
                )
            generations.add(gen.generation_id)
            requests.add(gen.request_id)
            operations.add(gen.operation.operation_id)
            uncertain = gen.status == "uncertain"
            interrupted = gen.status == "failed" or (
                gen.status == "completed" and turn.decision is None
            )
            if turn.reading is not None:
                reading = turn.reading
                if reading.operation.operation_id in operations:
                    raise ValueError("Original read operation identity cannot repeat")
                operations.add(reading.operation.operation_id)
                uncertain = reading.outcome == "uncertain"
                interrupted = reading.outcome in ("failed", "returned_unconfirmed")
                if reading.outcome == "returned":
                    assert (
                        turn.decision is not None
                        and turn.decision.read_policy is not None
                    )
                    progress = observation_progress_from_turns(
                        self.turns[: len(generations)],
                        reading.request.snapshot,
                        turn.decision.read_policy,
                    )
                    interrupted = progress.controlled_stop is not None
            if event is not None:
                if (
                    event.action.action_id in actions
                    or event.operation.operation_id in operations
                ):
                    raise ValueError("Action and operation identities cannot repeat")
                actions.add(event.action.action_id)
                operations.add(event.operation.operation_id)
                uncertain = event.outcome == "uncertain"
                if event.outcome == "returned_incomplete":
                    interrupted = True
                    returned += 1
                if event.result is not None:
                    current = event.result.observation_ref
                    terminal = event.result.terminal
                    returned += 1
        if uncertain != (self.stop_reason == "uncertain") or terminal != (
            self.stop_reason == "finished"
        ):
            raise ValueError(
                "Trace stop reason must preserve uncertain or terminal facts"
            )
        if interrupted and self.stop_reason not in ("cancelled", "error"):
            raise ValueError(
                "Unprocessed response or failed generation must retain interruption"
            )
        if (
            self.stop_reason == "generation_limit"
            and self.generations != self.max_generations
        ):
            raise ValueError("Generation limit stop requires the actual limit")
        if (
            self.stop_reason == "interaction_limit"
            and self.interactions != self.max_interactions
        ):
            raise ValueError("Interaction limit stop requires the actual limit")
        return self


class TraceCommitUnconfirmed(RuntimeError):
    reason_code = "TRACE_COMMIT_UNCONFIRMED"

    def __init__(self, reference: EvidenceRef) -> None:
        self.reference = reference
        super().__init__(
            "Trace persisted; reconcile exact bytes without repeating model or browser actions"
        )
