"""Actual observation chains and raw call/return evidence, shared on both sides."""

from contextlib import nullcontext
from lab_generate_skill.ports.trace_body_inputs import (
    TraceSealingInputReads,
    VerifiedTraceReferenceReads,
)
from .trace_observation_inputs import TraceObservationReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.traces import TraceAuthority, InitialTraceObservationReads
from lab_generate_skill.domain.evidence_dependencies import evidence_references


class TraceEvidenceReader:
    def __init__(self, evidence: EvidenceReader, authority: TraceAuthority) -> None:
        self.reads, self.observations, self.authority = (
            StateReads(evidence),
            TraceObservationReader(evidence),
            authority,
        )

    def validate(
        self, trace: InteractionTrace, op: OperationContext, control: OperationControl
    ) -> None:
        trace = InteractionTrace.model_validate(trace)
        handoff = (
            self.authority.sealing_inputs(trace, op, self.reads.store, control)
            if isinstance(self.authority, TraceSealingInputReads)
            else nullcontext(self.reads.store)
        )
        with handoff as verified:
            self._validate(trace, op, control, verified)

    def _validate(
        self,
        trace: InteractionTrace,
        op: OperationContext,
        control: OperationControl,
        verified: EvidenceReader,
    ) -> None:
        reads, observations = StateReads(verified), TraceObservationReader(verified)
        scope = trace.scope
        if (op.run_id, op.owner_id) != (
            scope.owner.run_id,
            scope.owner.owner_id,
        ) or op.attempt_id not in (None, scope.attempt_id):
            raise OwnershipConflict("Trace belongs to another run/owner/attempt")
        initial = None
        if isinstance(self.authority, InitialTraceObservationReads):
            initial = self.authority.read_initial(
                trace.initial_observation_ref, op, control
            )
        for reference in dict.fromkeys(evidence_references((trace,))):
            if initial is None or reference != trace.initial_observation_ref:
                if not (
                    isinstance(verified, VerifiedTraceReferenceReads)
                    and verified.verify_trace_reference(reference, control)
                ):
                    reads.read(reference, control)
        if initial is None:
            initial = observations.load(trace.initial_observation_ref, control)
        initial.record.check_initial(scope.task, scope.context_id)
        observed = [initial]
        for turn in trace.turns:
            event = turn.interaction
            if event is not None and event.result is not None:
                observed.append(
                    observations.load(event.result.observation_ref, control)
                )
        ids: set[str] = set()
        for sequence, resolved in enumerate(observed):
            record = resolved.record
            if (record.task, record.context_id, record.attempt_id, record.sequence) != (
                scope.task,
                scope.context_id,
                scope.attempt_id,
                sequence,
            ) or record.observation_id in ids:
                raise OwnershipConflict(
                    "Trace observations must retain scope, unique IDs and contiguous sequences"
                )
            ids.add(record.observation_id)
        control.checkpoint()
        self.authority.verify(trace, tuple(observed), op)
        control.checkpoint()
