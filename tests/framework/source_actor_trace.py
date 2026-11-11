"""Actual completed model exchanges and browser returns at engineering trace gates."""

from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import (
    TraceProgressEvent,
    GenerationObserved,
    InteractionObserved,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import ResolvedObservation, Observation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls


class SourceTraceAuthority:
    def __init__(
        self,
        plan: TracePlan,
        store: EvidenceStore,
        controls: OperationControls,
        completed: list[LocalActorExecution],
    ) -> None:
        self.plan, self.store, self.controls, self.completed = (
            plan,
            store,
            controls,
            completed,
        )

    def verify_plan(self, plan: TracePlan, op: OperationContext) -> None:
        self.controls.bind(op).checkpoint()
        if plan != self.plan:
            raise OwnershipConflict("Original engineering trace plan changed")

    def verify_event(
        self, snapshot: TraceSnapshot, event: TraceProgressEvent, op: OperationContext
    ) -> None:
        self.verify_plan(snapshot.plan, op)
        control = self.controls.bind(op)
        if isinstance(event, GenerationObserved):
            gen = event.generation
            if gen.status == "completed" and not any(
                x.call.intent.generation_id == gen.generation_id
                and x.response_ref == gen.response_ref
                and x.call.intent.input_ref == gen.input_ref
                and x.call.intent.scope == gen.scope
                for x in self.completed
            ):
                raise OwnershipConflict(
                    "Generation has no verified actual registered-model exchange"
                )
        if (
            isinstance(event, InteractionObserved)
            and event.interaction.result is not None
        ):
            result = event.interaction.result
            raw = BrowserReadout.model_validate_json(
                self.store.read(result.return_ref, control)
            )
            observed = Observation.model_validate_json(
                self.store.read(result.observation_ref, control)
            )
            if (
                raw.observation != observed
                or raw.action != event.interaction.action
                or raw.operation != event.interaction.operation
                or raw.scope != self.plan.scope
            ):
                raise OwnershipConflict(
                    "Original browser return differs from recorded interaction"
                )

    def verify(
        self,
        trace: InteractionTrace,
        observations: tuple[ResolvedObservation, ...],
        op: OperationContext,
    ) -> None:
        self.controls.bind(op).checkpoint()
        if (
            trace.scope != self.plan.scope
            or trace.initial_observation_ref != self.plan.initial_observation_ref
            or not observations
            or observations[0].record.sequence != 0
        ):
            raise OwnershipConflict(
                "Sealed engineering trace changed original initial observation"
            )
