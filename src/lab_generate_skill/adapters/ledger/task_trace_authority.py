"""Original task trace provenance over retained physical owners and actual returns."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from .task_trace_inputs import TaskTraceEventInputs
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import (
    TraceProgressEvent,
    GenerationObserved,
    InteractionObserved,
    GenerationPlanned,
    ActionPlanned,
    ReadPlanned,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import ResolvedObservation, Observation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.adapters.plans.state_reads import StateReads


class OriginalTaskTraceAuthority:
    def __init__(
        self,
        resources: OriginalTaskResourceOwner,
        plan: TracePlan,
        completed: Callable[[], tuple[LocalActorExecution, ...]],
    ) -> None:
        if not isinstance(resources, OriginalTaskResourceOwner) or not callable(
            completed
        ):
            raise TypeError(
                "Original task resource and model exchange supplier required"
            )
        self.resources, self.plan, self.completed = (
            resources,
            TracePlan.model_validate(plan),
            completed,
        )
        if self.plan.binding != resources.plan.intent.binding:
            raise OwnershipConflict("Trace replaced original task binding")
        self._trace_inputs: TaskTraceEventInputs | None = None
        if resources.inputs is not None:
            if resources.inputs.trace_inputs is not None:
                raise OwnershipConflict("Original trace body binding is one-shot")
            self._trace_inputs = TaskTraceEventInputs(self.plan, resources.inputs)
            resources.inputs.trace_inputs = self._trace_inputs

    def event_inputs(
        self,
        before: TraceSnapshot,
        event: TraceProgressEvent,
        op: OperationContext,
        original: EvidenceReader,
        control: OperationControl,
    ) -> AbstractContextManager[EvidenceReader]:
        return (
            nullcontext(original)
            if self._trace_inputs is None
            else self._trace_inputs.event_inputs(before, event, op, original, control)
        )

    def sealing_inputs(
        self,
        trace: InteractionTrace,
        op: OperationContext,
        original: EvidenceReader,
        control: OperationControl,
    ) -> AbstractContextManager[EvidenceReader]:
        return (
            nullcontext(original)
            if self._trace_inputs is None
            else self._trace_inputs.sealing_inputs(trace, op, original, control)
        )

    def verify_plan(self, plan: TracePlan, op: OperationContext) -> None:
        r = self.resources
        if plan != self.plan:
            raise OwnershipConflict("Original trace plan changed")
        control = r.site.controls.bind(op)
        run = r.require(op, control, live=False)
        if (
            plan.max_generations != run.resources.max_actor_generations_per_attempt
            or plan.max_interactions != run.resources.max_interactions_per_attempt
        ):
            raise OwnershipConflict("Trace changed frozen original Actor limits")

    def read_initial(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> ResolvedObservation | None:
        r = self.resources
        held = r.inputs
        if held is None:
            return None
        held.check(op, control)
        initial = held.initial
        measured = held.candidate_baseline
        if (
            initial is None
            or measured is None
            or (
                reference != self.plan.initial_observation_ref
                or reference != initial.acquired.details.started.initial_observation_ref
                or measured[0].observation_ref != reference
                or measured[0].observation != initial.observation.record
            )
        ):
            raise OwnershipConflict(
                "Trace changed original measured initial observation"
            )
        r.owner.require(op, control, new_work=False)
        require_complete_bytes(
            reference, initial.observation.record.model_dump_json().encode()
        )
        control.checkpoint()
        return ResolvedObservation.model_validate(initial.observation)

    def verify_event(
        self, snapshot: TraceSnapshot, event: TraceProgressEvent, op: OperationContext
    ) -> None:
        self.verify_plan(snapshot.plan, op)
        r, control = self.resources, self.resources.site.controls.bind(op)
        if isinstance(event, (GenerationPlanned, ActionPlanned, ReadPlanned)):
            r.require_browser(op, control)
        if (
            isinstance(event, GenerationObserved)
            and event.generation.status == "completed"
        ):
            gen = event.generation
            if not any(
                x.call.intent.generation_id == gen.generation_id
                and x.response_ref == gen.response_ref
                and x.call.intent.input_ref == gen.input_ref
                and x.call.intent.scope == gen.scope
                for x in self.completed()
            ):
                raise OwnershipConflict(
                    "Generation has no original registered-model exchange"
                )
        if (
            isinstance(event, InteractionObserved)
            and event.interaction.result is not None
        ):
            result = event.interaction.result
            inputs = self.interaction_inputs(event, op, control)
            reads = r.owner.reads if inputs is None else StateReads(inputs)
            raw = reads.parse(
                result.return_ref, "browser-step-return/1", BrowserReadout, control
            )
            observed = reads.parse(
                result.observation_ref,
                "observation/1",
                Observation,
                control,
                visibility="public",
            )
            if (
                raw.observation != observed
                or raw.action != event.interaction.action
                or raw.operation != event.interaction.operation
                or raw.scope != self.plan.scope
            ):
                raise OwnershipConflict(
                    "Interaction differs from original browser return"
                )

    def interaction_inputs(
        self,
        event: InteractionObserved,
        op: OperationContext,
        control: OperationControl,
    ) -> EvidenceReader | None:
        r = self.resources
        if r.inputs is None or event.interaction.result is None:
            return None
        r.inputs.check(op, control)
        r.owner.require(op, control, new_work=False)
        browser = r.browser()
        if browser is None:
            raise OwnershipConflict("Interaction has no original browser")
        published = browser.session.published_step
        if published is None or published.result != event.interaction.result:
            raise OwnershipConflict("Interaction has no exact original published step")
        raw = BrowserReadout.model_validate_json(published.bodies[1].raw)
        if (raw.action, raw.operation, raw.scope) != (
            event.interaction.action,
            event.interaction.operation,
            self.plan.scope,
        ):
            raise OwnershipConflict("Published interaction changed original action")
        r.inputs.check(op, control)
        return published

    def verify(
        self,
        trace: InteractionTrace,
        observations: tuple[ResolvedObservation, ...],
        op: OperationContext,
    ) -> None:
        self.verify_plan(self.plan, op)
        if (
            trace.scope != self.plan.scope
            or trace.initial_observation_ref != self.plan.initial_observation_ref
            or not observations
            or observations[0].record.sequence != 0
        ):
            raise OwnershipConflict("Sealed trace changed original unique initial view")
        control = self.resources.site.controls.bind(op)
        held = self.read_initial(self.plan.initial_observation_ref, op, control)
        original = (
            held.record
            if held is not None
            else self.resources.owner.reads.parse(
                self.plan.initial_observation_ref,
                "observation/1",
                Observation,
                control,
                visibility="public",
            )
        )
        if observations[0].record != original:
            raise OwnershipConflict(
                "Trace initial observation differs from original bytes"
            )
