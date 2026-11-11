"""Read saved original construction commands; never create IDs or invoke work."""

from .state_reads import StateReads
from lab_generate_skill.domain.construction_control import ConstructionStepPlan
from lab_generate_skill.domain.construction_preparation import PublishedConstructionStep
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


class EvidenceConstructionSteps:
    def __init__(self, evidence: EvidenceReader) -> None:
        if evidence is None:
            raise ValueError("Original readonly construction CAS required")
        self.reads = StateReads(evidence)

    def load(
        self,
        reference: EvidenceRef,
        run: RunBinding,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> PublishedConstructionStep:
        reference = EvidenceRef.model_validate(reference)
        run, op = RunBinding.model_validate(run), OperationContext.model_validate(
            operation
        )
        if (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
        ) != (run.owner.run_id, run.owner.owner_id, None, None, None):
            raise OwnershipConflict(
                "Construction step read requires original run-level owner"
            )
        private_state_ref(reference, "construction-step-plan/1")
        if (
            reference.media_type != "application/json"
            or not 0 < reference.size_bytes <= 4 * 1024**2
        ):
            raise EvidenceIntegrityError("Canonical private step JSON required")
        raw = self.reads.read(reference, control)
        step = ConstructionStepPlan.model_validate_json(raw)
        if step.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Complete original canonical step required")
        if step.run != run or (
            op != step.operation
            and not (
                op.mode == "cleanup"
                and op.parent_operation_id == step.operation.operation_id
            )
        ):
            raise OwnershipConflict(
                "Step read requires original operation or its bounded cleanup, never rebinding"
            )
        return PublishedConstructionStep(reference=reference, step=step)
