"""Bounded original private bytes to explicit current navigation task data."""

from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.ports.state_qualification import (
    StateQualificationAuthority,
    StateQualificationChecks,
)
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_checks import (
    NavigationStateChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)


from lab_generate_skill.adapters.plans.admin_native_input import decode_admin_native
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.preparation_records import PreparationAuthority
from lab_generate_skill.sites.shopping_admin.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationInputs,
)


def load_admin_navigation_inputs(
    raw: bytes, reference: EvidenceRef, public: PublicTask
) -> AdminNavigationInputs:
    return bind_admin_navigation(decode_admin_native(raw, reference), reference, public)


def admin_navigation_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    """Join existing records with navigation checks; authority remains mandatory."""
    return EvidencePreparationRecords(
        store, controls, bindings, NavigationPreparationChecks(store), authority
    )


def admin_navigation_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
    *,
    checks: StateQualificationChecks | None = None,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store,
        controls,
        NavigationStateChecks(store) if checks is None else checks,
        authority,
    )


def admin_navigation_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store, controls, preparations, NavigationInitialObservationChecks(), authority
    )
