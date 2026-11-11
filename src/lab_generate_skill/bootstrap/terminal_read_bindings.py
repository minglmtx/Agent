"""Exact navigation terminal consumers; supplied initial data never grants effects."""

from lab_generate_skill.domain.terminal_read import (
    TerminalReadRequest,
    TerminalReadBodies,
    TerminalEvidenceBody,
)
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from typing import Literal
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.preparation import PreparedTask
from .admin_navigation_terminal import read_admin_navigation_terminal
from .map_navigation_terminal import read_map_navigation_terminal


class _InitialBody:
    def __init__(self, request: TerminalReadRequest) -> None:
        self.request = request

    def load(
        self,
        selection: InitialObservationSelection,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitialObservationInputs:
        control.checkpoint()
        if (
            selection != self.request.initial.selection
            or operation != self.request.operation
        ):
            raise OwnershipConflict(
                "Terminal initial handoff changed original selection/operation"
            )
        return self.request.initial


class _NoPreparation:
    def publish(
        self, selection: PreparationSelection, op: OperationContext
    ) -> PreparedPublication:
        raise PermissionError("Terminal proof cannot publish preparation")

    def load(
        self, publication: PreparedPublication, op: OperationContext
    ) -> PreparedTask:
        raise PermissionError(
            "Terminal proof requires supplied complete initial output"
        )


class _TerminalBodies:
    def __init__(self, original: EvidenceReader) -> None:
        self.original = original
        self.bodies: dict[EvidenceRef, TerminalEvidenceBody] = {}

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        raw = self.original.read(ref, control)
        body = TerminalEvidenceBody(reference=ref, json_text=raw.decode())
        old = self.bodies.get(ref)
        if old is not None and old != body:
            raise OwnershipConflict("Original terminal body changed during proof")
        if old is None and (
            len(self.bodies) >= 256
            or sum(v.reference.size_bytes for v in self.bodies.values()) + len(raw)
            > 13 * 1024**2
        ):
            raise ValueError("Complete terminal dependency handoff exceeds bound")
        self.bodies[ref] = body
        return raw


def read_terminal_bodies(
    request: TerminalReadRequest,
    evidence: EvidenceReader,
    control: OperationControl,
    *,
    purpose: Literal["same_task", "retained_data"] = "same_task",
) -> TerminalReadBodies:
    request = TerminalReadRequest.model_validate(request)
    task = request.initial.prepared.scope.task
    key = task.site, task.family, task.contract_version, task.split
    bindings = (
        (("shopping_admin", "page_navigation", 1, "train"), "admin"),
        (("map", "navigation_page_identity", 1, "train"), "map"),
    )
    selected = [kind for binding, kind in bindings if binding == key]
    if len(selected) != 1:
        raise OwnershipConflict("Exactly one installed terminal consumer required")
    reader = _TerminalBodies(evidence)
    initials, preparation = _InitialBody(request), _NoPreparation()
    if selected[0] == "admin":
        read_admin_navigation_terminal(
            reader,
            preparation,
            request.terminal_ref,
            request.contract,
            request.operation,
            control,
            initials=initials,
        )
    else:
        read_map_navigation_terminal(
            reader,
            preparation,
            request.terminal_ref,
            request.operation,
            control,
            initials=initials,
        )
    control.checkpoint()
    return TerminalReadBodies(
        request=request, purpose=purpose, bodies=tuple(reader.bodies.values())
    )


def require_complete_terminal_bodies(
    bodies: TerminalReadBodies, control: OperationControl
) -> None:
    """Recheck the exact installed consumer using returned bytes only, no I/O."""
    bodies = TerminalReadBodies.model_validate(bodies)
    values = {body.reference: body.json_text.encode() for body in bodies.bodies}

    class ReturnedBodies:
        def read(self, reference: EvidenceRef, bounded: OperationControl) -> bytes:
            bounded.checkpoint()
            try:
                return values[reference]
            except KeyError as error:
                raise EvidenceIntegrityError(
                    "Terminal proof omitted an original complete dependency"
                ) from error

    expected = read_terminal_bodies(
        bodies.request, ReturnedBodies(), control, purpose=bodies.purpose
    )
    if {value.reference: value.json_text for value in expected.bodies} != {
        value.reference: value.json_text for value in bodies.bodies
    }:
        raise EvidenceIntegrityError("Terminal proof changed its exact dependency set")
