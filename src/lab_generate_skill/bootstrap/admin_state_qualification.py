"""Fixed selected-task state checks; callers must supply actual authority."""

from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_state_checks import (
    ProductStateChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.state_qualification import StateQualificationAuthority


def admin_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store, controls, ProductStateChecks(store), authority
    )
