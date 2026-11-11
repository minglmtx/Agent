"""Actual cleanup owner over the existing once-only task finalization producer."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .task_finalization_inputs import read_finalization_declaration


class OriginalTaskFinalizationAuthority:
    def __init__(
        self,
        resources: OriginalTaskResourceOwner,
        finalization: Callable[[], RecordedTaskFinalization],
    ) -> None:
        if not isinstance(resources, OriginalTaskResourceOwner) or not callable(
            finalization
        ):
            raise TypeError("Original task resource/finalization supplier required")
        self.resources, self.finalization = resources, finalization

    def read_finalization_declaration(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> bytes:
        return read_finalization_declaration(
            self.resources,
            self.finalization(),
            plan,
            declaration,
            reference,
            operation,
            control,
        )

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        r, f = self.resources, self.finalization()
        if (
            not isinstance(f, RecordedTaskFinalization)
            or plan != r.plan
            or f.plan != plan
            or f.declaration != declaration
            or operation.mode != "cleanup"
            or declaration.scope != f.reset.scope
        ):
            raise OwnershipConflict("Cleanup replaced original task/finalization")
        r.require(operation, control, live=False)
        expected = tuple(
            dict.fromkeys(
                (
                    *f.preparation.state.references,
                    *f.state.references,
                    *f.browser.references,
                )
            )
        )
        if any(ref not in expected for ref in references):
            raise OwnershipConflict("Cleanup changed original producer reference set")

        # Only this finalizer's confirmed producer references, within the same
        # owned invocation. Current resource/claim/storage checks ran above;
        # a retained body grants neither another restore nor a storage permit.
        held = r.inputs
        bodies: dict[EvidenceRef, bytes] = {}
        if held is not None:
            held.check(operation, control)
            if held.finalization is None:
                held.finalization = (f, {})
            producer, bodies = held.finalization
            if producer is not f or any(ref not in expected for ref in bodies):
                raise OwnershipConflict("Cleanup changed original body producer")

        def read(reference: EvidenceRef) -> bytes:
            control.checkpoint()
            raw = bodies.get(reference)
            if raw is None:
                raw = r.owner.reads.read(reference, control)
                require_complete_bytes(reference, raw)
                bodies[reference] = raw
            else:
                require_complete_bytes(reference, raw)
            if held is not None:
                held.check(operation, control)
            return raw

        for reference in references:
            read(reference)
        s = f.state
        # The native/resume suppliers also consume these same once-only
        # producer requests. This check grants no replacement request or retry.
        for value, ref in (
            (s.restore_request, s.restore_request_ref),
            (s.resume_request, s.resume_request_ref),
        ):
            if value is not None and operation == value.operation:
                if (
                    ref is None
                    or ref not in references
                    or read(ref) != value.model_dump_json().encode()
                ):
                    raise OwnershipConflict(
                        "Cleanup changed original persisted request"
                    )
                if s.closed is None:
                    raise OwnershipConflict(
                        "Native recovery requires confirmed browser close"
                    )
                r.verify_closed(plan, s.closed, operation, control)
        control.checkpoint()
