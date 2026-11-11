"""Selected SSH records assembled on current ports with mandatory authorities."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from .gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from lab_generate_skill.sites.gitlab.tasks.ssh_key_browser_binding import (
    SshKeyBrowserChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindings, TaskBindingAuthority
from lab_generate_skill.ports.preparation_records import PreparationAuthority
from lab_generate_skill.sites.gitlab.tasks.ssh_key_binding import SshKeyBindingAuthority
from lab_generate_skill.sites.gitlab.tasks.ssh_key_preparation_checks import (
    SshKeyPreparationChecks,
)
from .gitlab_ssh_key import load_ssh_key_inputs
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state_checks import SshKeyStateChecks
from lab_generate_skill.sites.gitlab.tasks.ssh_key_initial_observation import (
    SshKeyInitialObservationChecks,
)
from lab_generate_skill.ports.state_qualification import StateQualificationAuthority
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.preparation_records import PreparationRecords


def gitlab_prepared_browser_checks(store: EvidenceStore) -> PreparedBrowserTaskChecks:
    return SshKeyBrowserChecks(store, load_ssh_key_state)


def bind_ssh_key_records(
    store: EvidenceStore, controls: OperationControls, authority: TaskBindingAuthority
) -> TaskBindings:
    return EvidenceTaskBindings(
        store, controls, SshKeyBindingAuthority(store, load_ssh_key_inputs, authority)
    )


def ssh_key_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    return EvidencePreparationRecords(
        store,
        controls,
        bindings,
        SshKeyPreparationChecks(store, load_ssh_key_state),
        authority,
    )


def gitlab_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store, controls, SshKeyStateChecks(store, load_ssh_key_state), authority
    )


def gitlab_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store, controls, preparations, SshKeyInitialObservationChecks(), authority
    )
