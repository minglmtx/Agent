"""Bind the existing deferred preparation to a fresh whole-graph reader."""

from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.preparation_records import (
    PreparationRecords,
    PreparationInputReads,
    LoadedPreparedTask,
)
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.lifecycle import OperationContext
from .deferred_state_records import DeferredPreparationRecords
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.sites.task_preparation_record_inputs import (
    TaskPreparationRecordInputs,
)
from lab_generate_skill.ports.contexts import ContextFactReads


class OwnedPreparationRecords(DeferredPreparationRecords):
    """Expose the receipt port only for this exact owned graph-reader factory."""

    def load_with_receipt(
        self, publication: PreparedPublication, op: OperationContext
    ) -> LoadedPreparedTask:
        original = self.original()
        if not isinstance(original, EvidencePreparationRecords):
            raise OwnershipConflict("Original complete preparation reader required")
        return original.load_with_receipt(publication, op)


def owned_preparation_records(
    records: PreparationRecords,
    reads: PreparationInputReads,
    *,
    inputs: TaskInitializationInputs | None = None,
) -> DeferredPreparationRecords:
    if not isinstance(records, DeferredPreparationRecords):
        raise TypeError("Original deferred preparation producer required")
    handoff = None
    if inputs is not None:
        if (
            not isinstance(reads, ContextFactReads)
            or inputs.preparation_records is not None
        ):
            raise OwnershipConflict(
                "Original unique preparation current reader required"
            )
        handoff = TaskPreparationRecordInputs(inputs, reads)
        inputs.preparation_records = handoff

    def original() -> EvidencePreparationRecords:
        value = records.original()
        if not isinstance(value, EvidencePreparationRecords):
            raise OwnershipConflict("Original evidence preparation producer required")
        return EvidencePreparationRecords(
            value.store,
            value.controls,
            value.reader.bindings,
            value.checks,
            value.authority,
            input_reads=reads,
            record_inputs=handoff,
        )

    return OwnedPreparationRecords(original)
