"""Selected image records on existing ports with mandatory original authorities."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindings, TaskBindingAuthority
from lab_generate_skill.ports.preparation_records import (
    PreparationAuthority,
    PreparationRecords,
)
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from lab_generate_skill.sites.reddit.tasks.image_binding import ImageBindingAuthority
from lab_generate_skill.sites.reddit.tasks.image_preparation_checks import (
    ImagePreparationChecks,
)
from lab_generate_skill.sites.reddit.tasks.image_initial_observation import (
    ImageInitialObservationChecks,
)
from lab_generate_skill.sites.reddit.tasks.image_browser_binding import (
    ImageBrowserChecks,
)
from .reddit_native_image import load_image_inputs
from .reddit_browser_files import reddit_photo_plan


def bind_image_records(
    store: EvidenceStore, controls: OperationControls, authority: TaskBindingAuthority
) -> TaskBindings:
    return EvidenceTaskBindings(
        store, controls, ImageBindingAuthority(store, load_image_inputs, authority)
    )


def image_preparation_records(
    store: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: PreparationAuthority,
) -> EvidencePreparationRecords:
    return EvidencePreparationRecords(
        store, controls, bindings, ImagePreparationChecks(store), authority
    )


def reddit_prepared_browser_checks(store: EvidenceStore) -> PreparedBrowserTaskChecks:
    return ImageBrowserChecks(store, reddit_photo_plan)


def reddit_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store, controls, preparations, ImageInitialObservationChecks(), authority
    )


from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.ports.state_qualification import StateQualificationAuthority
from lab_generate_skill.sites.reddit.tasks.image_state_checks import ImageStateChecks


def reddit_state_qualifications(
    store: EvidenceStore,
    controls: OperationControls,
    authority: StateQualificationAuthority,
) -> EvidenceStateQualifications:
    return EvidenceStateQualifications(
        store, controls, ImageStateChecks(store), authority
    )
