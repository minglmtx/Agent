"""Fixed selected-family preparation-record assembly; no default authority."""

from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.sites.shopping_admin.tasks.product_preparation_checks import (
    ProductPreparationChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.preparation_records import PreparationAuthority


def admin_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    return EvidencePreparationRecords(
        store, controls, bindings, ProductPreparationChecks(store), authority
    )
