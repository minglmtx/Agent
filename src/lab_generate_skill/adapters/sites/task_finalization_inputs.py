"""Five frozen cleanup declarations within the existing owned task lifetime.

No permissions, source claims, native measurements or reset results are held.
The caller must complete original current admission before any cleanup effect.
"""

import os
import threading
from typing import TYPE_CHECKING
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes

if TYPE_CHECKING:
    from .task_finalization import RecordedTaskFinalization
    from .task_resource_owner import OriginalTaskResourceOwner


def read_finalization_declaration(
    resources: "OriginalTaskResourceOwner",
    finalization: "RecordedTaskFinalization",
    plan: TaskExecutionPlan,
    declaration: TaskFinalizationPlan,
    reference: EvidenceRef,
    operation: OperationContext,
    control: OperationControl,
) -> bytes:
    control.checkpoint()
    r, f = resources, finalization
    reference = EvidenceRef.model_validate(reference)
    if (
        f.owner != (os.getpid(), threading.get_ident())
        or plan != r.plan
        or f.plan != plan
        or f.declaration != declaration
        or operation.mode != "cleanup"
        or (operation.run_id, operation.owner_id, operation.attempt_id)
        != (plan.operation.run_id, plan.operation.owner_id, plan.operation.attempt_id)
    ):
        raise OwnershipConflict("Cleanup declarations left original task producer")
    expected: dict[EvidenceRef, bytes | None] = {
        plan.reset_plan_ref: f.reset.model_dump_json().encode(),
        plan.declaration_ref: f.preparation.declaration.model_dump_json().encode(),
        f.declaration_ref: declaration.model_dump_json().encode(),
        f.preparation.declaration.task_binding_ref: None,
    }
    if reference.content_schema == plan.schema_version:
        expected[reference] = plan.model_dump_json().encode()
    if (
        reference not in expected
        or reference.media_type != "application/json"
        or reference.visibility != "private"
        or reference.size_bytes > 2 * 1024**2
    ):
        raise OwnershipConflict(
            "Only exact original frozen cleanup declarations allowed"
        )
    held = r.inputs
    bodies: dict[EvidenceRef, bytes] = {}
    if held is not None:
        held.check(operation, control)
        if held.finalization_declarations is None:
            held.finalization_declarations = (f, {})
        producer, bodies = held.finalization_declarations
        if producer is not f:
            raise OwnershipConflict("Cleanup declaration producer changed")
    if reference not in bodies:
        if len(bodies) >= 5:
            raise EvidenceIntegrityError("Original cleanup declaration set exceeded")
        raw = r.owner.reads.read(reference, control)
        require_complete_bytes(reference, raw)
    else:
        raw = bodies[reference]
    require_complete_bytes(reference, raw)
    wanted = expected[reference]
    if reference == plan.reset_plan_ref:
        same = ResetPlan.model_validate_json(raw) == f.reset
    elif reference == plan.declaration_ref:
        same = (
            SiteTaskPreparationPlan.model_validate_json(raw)
            == f.preparation.declaration
        )
    else:
        same = wanted is None or raw == wanted
    if not same:
        raise OwnershipConflict("Cleanup declaration differs from original producer")
    if wanted is None:
        binding = TaskBinding.model_validate_json(raw)
        if binding.identity != plan.intent.binding.task:
            raise OwnershipConflict("Cleanup task binding changed original task")
    if held is not None:
        held.check(operation, control)
    bodies[reference] = raw
    control.checkpoint()
    return raw
