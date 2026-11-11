"""Existing ready-Baseline assembly before shared Actor dispatch, no new policy."""

from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.task import TaskBinding
from map_registered_worker_fixtures import RegisteredMapCase
from map_initial_records_fixtures import InitialCase
from map_prepared_records_fixtures import PreparedMapCase
from map_navigation_prepared_fixtures import NavigationPreparedCase
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from test_map_qualified_combination import StateAuthority
from test_slurm_commands import guard


def ready_baseline(original: RegisteredMapCase, i: InitialCase) -> None:
    ready_initial_baseline(original, i.preparation, i.records, i.selection, i.operation)


def ready_initial_baseline(
    original: RegisteredMapCase,
    p: PreparedMapCase | NavigationPreparedCase,
    records: EvidenceInitialObservations,
    selection: InitialObservationSelection,
    operation: OperationContext,
) -> tuple[BaselineInputs, EvidenceRef]:
    store = original.resource.evidence
    op = operation
    initial_ref = records.publish(selection, op)
    initial = records.load(selection, initial_ref, op)
    selected = records.reader.load(selection, op, guard())
    inputs = BaselineInputs(
        binding=TaskBinding.model_validate_json(store.read(original.binding)),
        public_task=selected.prepared.public_task,
        spec=selected.spec,
        spec_ref=selected.prepared.spec_ref,
        environment=p.environment,
        environment_ref=p.publication.selection.environment_ref,
        preparation=PreparationReceipt.model_validate_json(
            store.read(p.publication.preparation_ref)
        ),
        preparation_ref=p.publication.preparation_ref,
        prepared=selected.prepared,
        prepared_ref=p.publication.prepared_ref,
        observation=selected.returned.observation,
        observation_ref=initial.observation_ref,
        initial=initial,
        initial_ref=initial_ref,
    )
    operation = op.model_copy(update={"operation_id": "selected-ready-baseline"})
    baseline = assemble_baseline(inputs, operation)
    states = EvidenceStateRecords(
        store, original.resource.controls, StateAuthority(original)
    )
    reference = states.publish_baseline(baseline, operation)
    assert (
        states.load_baseline(reference, operation) == baseline
        and baseline.status == "ready"
    )
    return inputs, reference
