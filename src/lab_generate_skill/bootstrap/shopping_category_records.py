"""Original category recomputation with mandatory caller-owned binding rights."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority, TaskBindings
from lab_generate_skill.sites.shopping.tasks.navigation_binding import (
    CategoryNavigationBindingAuthority,
)
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.ports.preparation_records import (
    PreparationAuthority,
    PreparationRecords,
)
from lab_generate_skill.ports.state_qualification import StateQualificationAuthority
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.sites.shopping.tasks.navigation_preparation_checks import (
    CategoryNavigationPreparationChecks,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state_checks import (
    CategoryNavigationStateChecks,
)
from lab_generate_skill.sites.shopping.tasks.navigation_initial_observation import (
    CategoryNavigationInitialObservationChecks,
)


def bind_category_navigation_records(
    store: EvidenceStore, controls: OperationControls, authority: TaskBindingAuthority
) -> TaskBindings:
    return EvidenceTaskBindings(
        store,
        controls,
        CategoryNavigationBindingAuthority(
            store, load_category_navigation_inputs, authority
        ),
    )


def category_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    return EvidencePreparationRecords(
        store, controls, bindings, CategoryNavigationPreparationChecks(store), authority
    )


def category_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store, controls, CategoryNavigationStateChecks(store), authority
    )


def category_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store,
        controls,
        preparations,
        CategoryNavigationInitialObservationChecks(),
        authority,
    )
