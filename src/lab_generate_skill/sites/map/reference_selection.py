"""Bind one eligible terminal response to its original prepared inspection.

These are data checks, not source/resource authority. Only the parent can read
browser files; the site worker reads the exact selected CAS declarations after
the existing original controller has verified live capture authority.
"""

from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_reference_selection import MapReferenceSelection
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_bounds import request_bounds
from .terminal_evidence import TerminalMapEvidence
from .terminal_files import private_record
from .terminal_requests import reference_candidates
from .tasks.overlay_admission import task_input
from .tasks.state_admission import same_task
from .tasks.overlay_reference_policy import (
    original_reference_bounds,
    full_original_bbox_retained,
)


def inspection_binding(
    terminal_ref: EvidenceRef,
    inspection: SiteTaskRequest,
    store: EvidenceReader,
    control: OperationControl,
) -> MapTerminalSelection:
    inspection = SiteTaskRequest.model_validate(inspection)
    task_input(inspection)
    if inspection.action != "inspect":
        raise OwnershipConflict("Map reference requires original read-only inspection")
    selected = private_record(
        store, terminal_ref, "map-terminal-selection/1", MapTerminalSelection, control
    )
    prepared = private_record(
        store,
        selected.initial.preparation.selection.request_ref,
        "site-task-request/2",
        SiteTaskRequest,
        control,
    )
    same_task(inspection, prepared)
    if (
        prepared.action != "prepare"
        or inspection.snapshot_ref != prepared.snapshot_ref
        or inspection.operation.operation_id == prepared.operation.operation_id
    ):
        raise OwnershipConflict("Map reference changed original preparation/snapshot")
    return selected


def select_reference(
    terminal_ref: EvidenceRef,
    terminal: TerminalMapEvidence,
    inspection: SiteTaskRequest,
    request_index: int,
    store: EvidenceReader,
    control: OperationControl,
) -> MapReferenceSelection:
    inspection = SiteTaskRequest.model_validate(inspection)
    if type(request_index) is not int or not 0 <= request_index <= 255:
        raise ValueError("Original bounded Map request index required")
    selected = inspection_binding(terminal_ref, inspection, store, control)
    if selected != terminal.selection:
        raise OwnershipConflict("Map reference changed original terminal capture")
    candidate = next(
        (
            r
            for r in reference_candidates(terminal, control).selected
            if r.index == request_index
        ),
        None,
    )
    if candidate is None:
        raise ValueError(
            "Original Map request is not eligible for independent DB capture"
        )
    return MapReferenceSelection(
        inspection_sha256=inspection.digest,
        terminal_selection_ref=terminal_ref,
        terminal_handle=terminal.publication.handle,
        request_index=candidate.index,
        bounds=candidate.bounds,
        response_kind=candidate.response_kind,
        payload=candidate.payload,
        records_sha256=candidate.records_sha256,
    )


def read_reference_selection(
    store: EvidenceReader,
    reference: EvidenceRef,
    inspection: SiteTaskRequest,
    control: OperationControl,
) -> MapReferenceSelection:
    reference = EvidenceRef.model_validate(reference)
    inspection = SiteTaskRequest.model_validate(inspection)
    if not 0 < reference.size_bytes <= 64 * 1024:
        raise EvidenceIntegrityError("Bounded private Map selection required")
    selected = private_record(
        store, reference, "map-reference-selection/1", MapReferenceSelection, control
    )
    terminal = inspection_binding(
        selected.terminal_selection_ref, inspection, store, control
    )
    original = original_reference_bounds(
        store, terminal.original_reference_ref, control
    )
    if (
        selected.inspection_sha256 != inspection.digest
        or request_bounds(selected.bounds) != selected.bounds
        or not full_original_bbox_retained(selected.bounds, original)
    ):
        raise OwnershipConflict(
            "Map selection changed inspection or full original region"
        )
    return selected


def verify_reference_selection(
    selected: MapReferenceSelection,
    terminal: TerminalMapEvidence,
    inspection: SiteTaskRequest,
    store: EvidenceReader,
    control: OperationControl,
) -> None:
    selected = MapReferenceSelection.model_validate(selected)
    expected = select_reference(
        selected.terminal_selection_ref,
        terminal,
        inspection,
        selected.request_index,
        store,
        control,
    )
    if selected != expected:
        raise EvidenceIntegrityError(
            "Map selection does not match complete original response"
        )
    control.checkpoint()
