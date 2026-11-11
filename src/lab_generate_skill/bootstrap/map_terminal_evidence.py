"""Original prepared browser and controller-owned complete terminal file reads."""

from pathlib import Path
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.browsergym.storage_original import (
    OriginalBrowserAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.browser_access import (
    OriginalMapBrowserAccess,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.sites.map.terminal_evidence import (
    terminal_evidence,
    TerminalMapEvidence,
)
from lab_generate_skill.sites.map.terminal_files import private_record


def map_terminal_evidence(
    store: EvidenceReader,
    controls: OperationControls,
    preparations: PreparationRecords,
    selection_ref: EvidenceRef,
    operation: OperationContext,
) -> TerminalMapEvidence:
    operation = OperationContext.model_validate(operation)
    control = controls.bind(operation)
    return read_map_terminal_evidence(
        store, preparations, selection_ref, operation, control
    )


def read_map_terminal_evidence(
    store: EvidenceReader,
    preparations: PreparationRecords,
    selection_ref: EvidenceRef,
    operation: OperationContext,
    control: OperationControl,
) -> TerminalMapEvidence:
    selection = private_record(
        store, selection_ref, "map-terminal-selection/1", MapTerminalSelection, control
    )
    initial = InitialObservationReader(store, preparations).load(
        selection.initial, operation, control
    )
    scope = initial.prepared.scope
    if (operation.run_id, operation.owner_id, operation.attempt_id) != (
        scope.owner.run_id,
        scope.owner.owner_id,
        scope.attempt_id,
    ):
        raise OwnershipConflict("Map terminal read changed original attempt")
    access = OriginalMapBrowserAccess(
        initial.browser.configuration,
        "controller",
        OriginalBrowserAcquisitionReader(),
        None,
    )
    files = MapArtifactReader(access.plan, Path(access.plan.workspace_root), access)
    return terminal_evidence(selection, initial, store, files, control)
