"""Group records use current common ports and mandatory original authorities."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority, TaskBindings
from lab_generate_skill.ports.preparation_records import (
    PreparationAuthority,
    PreparationRecords,
)
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from lab_generate_skill.sites.gitlab.tasks.group_binding import GroupBindingAuthority
from lab_generate_skill.sites.gitlab.tasks.group_preparation_checks import (
    GroupPreparationChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_browser_binding import (
    GroupBrowserChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_initial_observation import (
    GroupInitialObservationChecks,
)
from .gitlab_group import load_group_inputs
from .gitlab_group_capture import load_group_capture
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.ports.state_qualification import (
    StateQualificationAuthority,
    StateQualificationChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_state_checks import GroupStateChecks


def bind_group_records(
    store: EvidenceStore, controls: OperationControls, authority: TaskBindingAuthority
) -> TaskBindings:
    return EvidenceTaskBindings(
        store, controls, GroupBindingAuthority(store, load_group_inputs, authority)
    )


def group_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    return EvidencePreparationRecords(
        store,
        controls,
        bindings,
        GroupPreparationChecks(store, load_group_capture),
        authority,
    )


def group_prepared_browser_checks(store: EvidenceStore) -> PreparedBrowserTaskChecks:
    return GroupBrowserChecks(store, load_group_capture)


def group_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store, controls, preparations, GroupInitialObservationChecks(), authority
    )


def group_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
    *,
    checks: StateQualificationChecks | None = None,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store,
        controls,
        GroupStateChecks(store, load_group_capture) if checks is None else checks,
        authority,
    )
