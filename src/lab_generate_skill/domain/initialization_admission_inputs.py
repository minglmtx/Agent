"""Immutable canonical producer bodies for one initialization call, no rights."""

from dataclasses import dataclass
import hashlib
from .evidence import EvidenceRef
from .task_initialization import TaskInitializationPlan
from .task_preparation import SiteTaskPrepared, SiteTaskPreparationPlan
from .task_site_acquisition import SiteTaskAcquired
from .task_execution import TaskExecutionPlan
from .task import TaskBinding
from .reset import ResetPlan
from .errors import OwnershipConflict


@dataclass(frozen=True)
class InitializationAdmissionInputs:
    declaration_ref: EvidenceRef
    declaration: TaskInitializationPlan
    prepared: SiteTaskPrepared
    preparation: SiteTaskPreparationPlan
    acquired: SiteTaskAcquired
    binding: TaskBinding
    reset: ResetPlan

    def require_original(
        self,
        plan: TaskExecutionPlan,
        declaration_ref: EvidenceRef,
        declaration: TaskInitializationPlan,
    ) -> None:
        if (
            self.declaration_ref != declaration_ref
            or self.declaration != declaration
            or self.prepared.declaration_ref != plan.declaration_ref
            or self.acquired.declaration_ref != plan.declaration_ref
        ):
            raise OwnershipConflict(
                "Initialization bodies changed full original references"
            )
        # These are the actual canonical publisher outputs, not relabelled
        # historical artifacts. Full reference metadata is checked as well.
        pairs: tuple[
            tuple[
                EvidenceRef,
                TaskInitializationPlan
                | SiteTaskPrepared
                | SiteTaskPreparationPlan
                | SiteTaskAcquired
                | TaskBinding
                | ResetPlan,
            ],
            ...,
        ] = (
            (declaration_ref, declaration),
            (declaration.prepared_result_ref, self.prepared),
            (plan.declaration_ref, self.preparation),
            (self.prepared.acquired_ref, self.acquired),
            (self.preparation.task_binding_ref, self.binding),
            (plan.reset_plan_ref, self.reset),
        )
        for reference, body in pairs:
            if (reference.content_schema, reference.visibility) != (
                body.schema_version,
                "private",
            ):
                raise OwnershipConflict(
                    "Initialization body schema or visibility differs"
                )
            raw = body.model_dump_json().encode()
            if (reference.size_bytes, reference.sha256) != (
                len(raw),
                hashlib.sha256(raw).hexdigest(),
            ):
                raise OwnershipConflict(
                    "Initialization body differs from complete original bytes"
                )
