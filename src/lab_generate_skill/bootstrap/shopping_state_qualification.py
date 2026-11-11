"""Shopping state semantics wired through the existing qualified-record port."""

from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state_checks import (
    OrderEtaStateChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.state_qualification import StateQualificationAuthority


def shopping_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store, controls, OrderEtaStateChecks(store), authority
    )
