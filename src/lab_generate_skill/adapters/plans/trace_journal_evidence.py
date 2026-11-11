"""Actual run plan, observation and outcome evidence at live journal boundaries."""

from contextlib import nullcontext
from lab_generate_skill.ports.trace_body_inputs import (
    TraceEventInputReads,
    VerifiedTraceReferenceReads,
)
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.trace_evidence import TraceEvidenceReader
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.trace_events import (
    GenerationPlanned,
    InteractionObserved,
    TraceProgressEvent,
    TraceSealed,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.trace_journal import TraceJournalAuthority
from lab_generate_skill.ports.trace_journal import TraceInteractionInputReads


class TraceJournalEvidence:
    def __init__(self, store: EvidenceReader, authority: TraceJournalAuthority) -> None:
        self.reads = StateReads(store)
        self.traces = TraceEvidenceReader(store, authority)
        self.authority = authority

    def plan(
        self,
        plan: TracePlan,
        op: OperationContext,
        control: OperationControl,
        *,
        generation_inputs: EvidenceReader | None = None,
    ) -> None:
        reader = self.reads.store if generation_inputs is None else generation_inputs
        reads = self.reads if generation_inputs is None else StateReads(reader)
        traces = (
            self.traces
            if generation_inputs is None
            else TraceEvidenceReader(reader, self.authority)
        )
        run = reads.parse(plan.binding.run.plan_ref, "run-plan/3", RunPlan, control)
        run.check_binding(plan.binding.run)
        if plan.binding.task not in tuple(task.identity for task in run.tasks) or (
            plan.max_generations,
            plan.max_interactions,
        ) != (
            run.resources.max_actor_generations_per_attempt,
            run.resources.max_interactions_per_attempt,
        ):
            raise OwnershipConflict(
                "Live trace differs from original run task or limits"
            )
        reads.dependencies((plan,), control)
        observed = traces.observations.load(
            plan.initial_observation_ref, control
        ).record
        observed.check_initial(plan.scope.task, plan.scope.context_id)
        if observed.attempt_id != plan.scope.attempt_id:
            raise OwnershipConflict(
                "Trace initial observation belongs to another attempt"
            )
        self.authority.verify_plan(plan, op)
        control.checkpoint()

    def event(
        self,
        before: TraceSnapshot,
        after: TraceSnapshot,
        event: TraceProgressEvent,
        op: OperationContext,
        control: OperationControl,
        *,
        generation_inputs: EvidenceReader | None = None,
    ) -> None:
        reader = self.reads.store if generation_inputs is None else generation_inputs
        if isinstance(event, InteractionObserved) and isinstance(
            self.authority, TraceInteractionInputReads
        ):
            supplied = self.authority.interaction_inputs(event, op, control)
            if supplied is not None:
                reader = supplied
        handoff = (
            self.authority.event_inputs(before, event, op, reader, control)
            if isinstance(self.authority, TraceEventInputReads)
            else nullcontext(reader)
        )
        with handoff as verified:
            self._event(before, after, event, op, control, verified)

    def _event(
        self,
        before: TraceSnapshot,
        after: TraceSnapshot,
        event: TraceProgressEvent,
        op: OperationContext,
        control: OperationControl,
        verified: EvidenceReader,
    ) -> None:
        reads = StateReads(verified)
        traces = TraceEvidenceReader(verified, self.authority)
        observations = traces.observations
        for reference in evidence_references(event):
            if not (
                isinstance(verified, VerifiedTraceReferenceReads)
                and verified.verify_trace_reference(reference, control)
            ):
                reads.read(reference, control)
        if isinstance(event, GenerationPlanned):
            observed = observations.load(
                event.intent.before_observation_ref, control
            ).record
            scope = before.plan.scope
            if (observed.task, observed.context_id, observed.attempt_id) != (
                scope.task,
                scope.context_id,
                scope.attempt_id,
            ):
                raise OwnershipConflict("Generation observation changed attempt scope")
        if (
            isinstance(event, InteractionObserved)
            and event.interaction.result is not None
        ):
            result = event.interaction.result
            previous = observations.load(result.before_observation_ref, control).record
            observed = observations.load(result.observation_ref, control).record
            scope = before.plan.scope
            if (
                observed.task,
                observed.context_id,
                observed.attempt_id,
                observed.sequence,
            ) != (
                scope.task,
                scope.context_id,
                scope.attempt_id,
                previous.sequence + 1,
            ) or observed.observation_id == previous.observation_id:
                raise OwnershipConflict(
                    "Action result must preserve consecutive observation identity"
                )
        if isinstance(event, TraceSealed):
            trace = after.project().sealed
            assert trace is not None
            traces.validate(trace, op, control)
        self.authority.verify_event(before, event, op)
        control.checkpoint()
