"""Shopping preparation records with mandatory binding and provenance authority."""

from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.sites.shopping.tasks.order_eta_preparation_checks import (
    OrderEtaPreparationChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.preparation_records import PreparationAuthority


def shopping_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    return EvidencePreparationRecords(
        store, controls, bindings, OrderEtaPreparationChecks(store), authority
    )
