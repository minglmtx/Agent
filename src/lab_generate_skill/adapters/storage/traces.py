"""Immutable recorded traces; late cleanup can save facts but cannot rerun work."""

from lab_generate_skill.adapters.plans.trace_evidence import TraceEvidenceReader
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace import InteractionTrace, TraceCommitUnconfirmed
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.traces import TraceAuthority


class EvidenceTraceRecords:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        authority: TraceAuthority,
    ) -> None:
        self.store, self.controls = store, controls
        self.reader = TraceEvidenceReader(store, authority)

    def publish(self, trace: InteractionTrace, op: OperationContext) -> EvidenceRef:
        trace = InteractionTrace.model_validate(trace)
        op = OperationContext.model_validate(op)
        original = trace.operation
        if op != original and not (
            op.mode == "cleanup"
            and op.parent_operation_id == original.operation_id
            and (
                op.run_id,
                op.owner_id,
                op.attempt_id,
                op.allocation_id,
                op.recovery_ref,
            )
            == (
                original.run_id,
                original.owner_id,
                original.attempt_id,
                original.allocation_id,
                original.recovery_ref,
            )
        ):
            raise OwnershipConflict(
                "Trace publication requires original command or scoped parent cleanup"
            )
        control = self.controls.bind(op)
        self.reader.validate(trace, op, control)
        control.checkpoint()
        ref = self.store.put(
            trace.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=trace.schema_version,
                visibility="private",
                producer="trace-records-v1",
            ),
            control=control,
        )
        try:
            control.checkpoint()
        except Exception as error:
            raise TraceCommitUnconfirmed(ref) from error
        return ref

    def load(self, ref: EvidenceRef, op: OperationContext) -> InteractionTrace:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        trace = self.reader.reads.parse(
            ref, "interaction-trace/1", InteractionTrace, control
        )
        self.reader.validate(trace, op, control)
        return trace
