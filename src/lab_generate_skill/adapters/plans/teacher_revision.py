"""Exact immutable revision-plan map/readback; no source grant, send or retries."""

from collections.abc import Mapping
from types import MappingProxyType
from lab_generate_skill.domain.teacher_revision import (
    TeacherRevisionPlan,
    BoundTeacherRevisionPlan,
)
from lab_generate_skill.domain.construction_inputs import RevisionInput
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_read_bound,
    require_complete_bytes,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.adapters.models.teacher_request_binding import (
    verify_teacher_wire_parameters,
)


def _read_plan_bytes(
    store: EvidenceReader, reference: EvidenceRef, limit: int, control: OperationControl
) -> bytes:
    require_complete_read_bound(reference, limit)
    control.checkpoint()
    raw = store.read(reference, control)
    require_complete_bytes(reference, raw)
    control.checkpoint()
    return raw


def publish_teacher_revision(
    plan: TeacherRevisionPlan, store: EvidenceStore, *, control: OperationControl
) -> EvidenceRef:
    plan = TeacherRevisionPlan.model_validate(plan)
    retained: list[EvidenceRef] = []
    try:
        raw = plan.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-revision-plan/1",
            visibility="private",
            producer="original-teacher-revision-plan",
        )
        candidate = evidence_reference(raw, metadata)
        retained.append(candidate)
        control.checkpoint()
        actual = EvidenceRef.model_validate(store.put(raw, metadata, control))
        if actual != candidate:
            retained.append(actual)
            raise EvidenceIntegrityError(
                "Context publication returned foreign metadata/reference"
            )
        if _read_plan_bytes(store, actual, len(raw), control) != raw:
            raise EvidenceIntegrityError(
                "Context publication readback differs from complete bytes"
            )
        control.checkpoint()
        return actual
    except BaseException as error:
        setattr(error, "teacher_plan_retained_refs", tuple(retained))
        raise


class EvidenceTeacherRevisionPlans:
    def __init__(
        self, references: Mapping[str, EvidenceRef], store: EvidenceReader
    ) -> None:
        if not references:
            raise ValueError("Explicit original Teacher plan bindings required")
        self.references = MappingProxyType(dict(references))
        self.store = store
        for ref in self.references.values():
            if (ref.visibility, ref.content_schema, ref.media_type) != (
                "private",
                "teacher-revision-plan/1",
                "application/json",
            ) or not 0 < ref.size_bytes <= 2 * 1024**2:
                raise ValueError("Bounded private original Teacher plan required")

    def load(
        self, request_id: str, operation: OperationContext, *, control: OperationControl
    ) -> BoundTeacherRevisionPlan:
        bound = self.load_recorded(request_id, operation, control=control)
        plan = bound.plan
        operation = OperationContext.model_validate(operation)
        original = plan.send.operation
        if operation.mode == "execute":
            if operation != original:
                raise OwnershipConflict(
                    "Teacher execution must retain exact original operation"
                )
        elif (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
            operation.parent_operation_id,
        ) != (
            original.run_id,
            original.owner_id,
            None,
            None,
            None,
            original.operation_id,
        ):
            raise OwnershipConflict(
                "Readonly Teacher review must address original run-level operation"
            )
        return bound

    def load_recorded(
        self, request_id: str, operation: OperationContext, *, control: OperationControl
    ) -> BoundTeacherRevisionPlan:
        control.checkpoint()
        if type(request_id) is not str or request_id not in self.references:
            raise OwnershipConflict(
                "No original Teacher call; new ID grants no execution"
            )
        ref = self.references[request_id]
        raw = _read_plan_bytes(self.store, ref, 2 * 1024**2, control)
        json_object(raw)
        plan = TeacherRevisionPlan.model_validate_json(raw)
        if (
            plan.model_dump_json().encode() != raw
            or plan.revision.request_id != request_id
        ):
            raise EvidenceIntegrityError("Original Teacher plan bytes/identity changed")
        operation = OperationContext.model_validate(operation)
        original = plan.send.operation
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
        ) != (original.run_id, original.owner_id, None, None, None):
            raise OwnershipConflict(
                "Recorded Teacher facts require their original run-level owner"
            )
        parameters = _read_plan_bytes(
            self.store,
            plan.send.parameters_ref,
            plan.send.limits.max_parameters_bytes,
            control,
        )
        verify_teacher_wire_parameters(parameters, plan)
        revision_raw = _read_plan_bytes(
            self.store, plan.call.input_ref, 1024**2, control
        )
        if (
            RevisionInput.model_validate_json(revision_raw) != plan.revision
            or revision_raw != plan.revision.model_dump_json().encode()
        ):
            raise EvidenceIntegrityError("Actual registered RevisionInput changed")
        fee = plan.preparation.profile.fee_scope_ref
        assert fee is not None
        if (
            _read_plan_bytes(self.store, fee, 1024**2, control)
            != plan.send.reservation.scope.model_dump_json().encode()
        ):
            raise EvidenceIntegrityError("Original fee scope bytes changed")
        return BoundTeacherRevisionPlan(reference=ref, plan=plan)
