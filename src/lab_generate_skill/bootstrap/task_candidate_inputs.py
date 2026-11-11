"""Read candidate facts from the actual completed late initializer, never predict."""

from typing import Generic, TypeVar
from lab_generate_skill.adapters.sites.task_initialized_inputs import (
    initialized_candidate_inputs,
)
from lab_generate_skill.adapters.plans.candidate_inputs import EvidenceCandidateInputs
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.actor_admission import CandidateFacts
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from .task_initialization import DeferredTaskInitialization

Initializer = TypeVar("Initializer", bound=RecordedTaskInitialization)


class InitializedTaskCandidateInputs(Generic[Initializer]):
    def __init__(
        self,
        initialization: DeferredTaskInitialization[Initializer],
        evidence: EvidenceStore,
        controls: OperationControls,
    ) -> None:
        if any(x is None for x in (initialization, evidence, controls)):
            raise ValueError("Original late initializer/evidence/controls required")
        self.initialization, self.evidence, self.controls = (
            initialization,
            evidence,
            controls,
        )

    def load(
        self, equivalence_ref: EvidenceRef, skill_ref: EvidenceRef, op: OperationContext
    ) -> CandidateFacts:
        original = self.initialization.original()
        result = original.state.result
        if (
            original.state.phase != "initialized"
            or result is None
            or result.equivalence_ref != equivalence_ref
            or original.plan.skill_ref != skill_ref
        ):
            raise OwnershipConflict(
                "Only actual completed original initial facts may enter admission"
            )
        if original.inputs is not None:
            return initialized_candidate_inputs(
                original, equivalence_ref, skill_ref, op, self.controls.bind(op)
            )
        return EvidenceCandidateInputs(
            self.evidence,
            original.contexts,
            original.states,
            EvidenceObservations(self.evidence, self.controls),
            self.controls,
        ).load(equivalence_ref, skill_ref, op)
