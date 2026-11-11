"""Persist one already-observed successful exchange; never sends or retries.

The admitted runtime supplies its original spec/acquired fact/guard and exact
channel bytes. Validate the complete candidate before CAS/index writes. Errors
retain the candidate and original exchange; a reference alone is not a commit.
This producer does not substitute for live resource or construction admission.
"""

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.generator_execution import GeneratorExecutionRecord
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.local_generator import LocalGeneratorIntent
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.generator_executions import GeneratorExecutions
from lab_generate_skill.ports.lifecycle import OperationControl
from .generator_worker_exchange import GeneratorWorkerExchange
from .generator_execution_evidence import verify_execution


class _CandidateEvidence:
    """Private read-only overlay; candidate bytes are immutable and hash checked."""

    def __init__(
        self, source: EvidenceStore, candidates: dict[EvidenceRef, bytes]
    ) -> None:
        self._source, self._candidates = source, candidates

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        if reference in self._candidates:
            return self._candidates[reference]
        return self._source.read(reference, control=control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        raise RuntimeError("Candidate validation must not write evidence")


def record_generator_exchange(
    store: EvidenceStore,
    records: GeneratorExecutions,
    spec: GeneratorResourceSpec,
    acquired_ref: EvidenceRef,
    intent: LocalGeneratorIntent,
    guard: ProcessOwnerGuard,
    exchange: GeneratorWorkerExchange,
    control: OperationControl,
) -> GeneratorExecutionRecord:
    spec = GeneratorResourceSpec.model_validate(spec)
    if not isinstance(exchange, GeneratorWorkerExchange):
        raise TypeError("Expected original immutable worker exchange")
    payloads = [
        (spec.model_dump_json().encode(), "generator-resource-spec/3"),
        (exchange.command, "generator-worker-command/3"),
        (exchange.reply, "generator-worker-reply/4"),
    ]
    candidates: dict[EvidenceRef, bytes] = {}
    metadata = []
    for raw, schema in payloads:
        meta = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="generator-execution-recorder-v1",
        )
        ref = evidence_reference(raw, meta)
        candidates[ref] = raw
        metadata.append((ref, raw, meta))
    record = GeneratorExecutionRecord(
        intent=intent,
        resource=spec.token,
        spec_ref=metadata[0][0],
        acquired_ref=acquired_ref,
        command_ref=metadata[1][0],
        reply_ref=metadata[2][0],
        guard=guard,
    )
    try:
        verify_execution(_CandidateEvidence(store, candidates), record, control)
        for reference, raw, meta in metadata:
            control.checkpoint()
            if store.put(raw, meta, control=control) != reference:
                raise EvidenceIntegrityError(
                    "Execution evidence publication identity differs"
                )
            control.checkpoint()
            if store.read(reference, control=control) != raw:
                raise EvidenceIntegrityError("Execution publication readback differs")
        records.publish(record, control)
        return record
    except BaseException as error:
        setattr(error, "generator_execution_candidate", record)
        setattr(error, "generator_execution_exchange", exchange)
        raise
