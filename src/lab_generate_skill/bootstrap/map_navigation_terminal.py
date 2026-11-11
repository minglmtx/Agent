"""Compose original initial and terminal readers; no site/reference DB ports."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.map_navigation_terminal import (
    MapNavigationTerminalSelection,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer
from lab_generate_skill.sites.map.terminal_files import private_record
from lab_generate_skill.sites.map.navigation_terminal_evidence import (
    NavigationTerminalEvidence,
    navigation_terminal_evidence,
)


def read_map_navigation_terminal(
    store: EvidenceReader,
    preparations: PreparationRecords,
    ref: EvidenceRef,
    operation: OperationContext,
    control: OperationControl,
    *,
    initials: InitialObservationReads | None = None,
) -> NavigationTerminalEvidence:
    operation = OperationContext.model_validate(operation)
    selection = private_record(
        store,
        ref,
        "map-navigation-terminal-selection/1",
        MapNavigationTerminalSelection,
        control,
    )
    reader = (
        InitialObservationReader(store, preparations) if initials is None else initials
    )
    initial = InitialObservationInputs.model_validate(
        reader.load(selection.initial, operation, control)
    )
    if initial.selection != selection.initial:
        raise OwnershipConflict("Navigation initial body changed exact selection")
    scope = initial.prepared.scope
    if (operation.run_id, operation.owner_id, operation.attempt_id) != (
        scope.owner.run_id,
        scope.owner.owner_id,
        scope.attempt_id,
    ):
        raise OwnershipConflict("Navigation terminal read changed original attempt")
    return navigation_terminal_evidence(
        selection,
        initial,
        store,
        control,
        reads=EvaluationEvidence(store, control),
        answer_reader=trace_answer,
    )
