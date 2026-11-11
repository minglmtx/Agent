"""Resolve actual candidate initial facts through qualified, injected ports."""

from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.actor_admission import CandidateFacts
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.ports.state_records import StateRecords


class EvidenceCandidateInputs:
    def __init__(
        self,
        evidence: EvidenceReader,
        contexts: ContextRecords,
        states: StateRecords,
        observations: Observations,
        controls: OperationControls,
    ) -> None:
        self.reads = StateReads(evidence)
        self.contexts, self.states, self.observations, self.controls = (
            contexts,
            states,
            observations,
            controls,
        )

    def load(
        self, equivalence_ref: EvidenceRef, skill_ref: EvidenceRef, op: OperationContext
    ) -> CandidateFacts:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        control.checkpoint()
        equivalence = self.contexts.load_equivalence(equivalence_ref, op)
        source = self.contexts.load_context(equivalence.source_context_receipt_ref, op)
        baseline = self.states.load_baseline(equivalence.candidate_baseline_ref, op)
        if baseline.scope != equivalence.scope:
            raise OwnershipConflict("Candidate input scope differs from equivalence")
        context = self.reads.parse(
            source.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        prepared = self.reads.parse(
            baseline.prepared_ref, "prepared-task/1", PreparedTask, control
        )
        binding = self.reads.parse(
            prepared.task_binding_ref, "task-binding/1", TaskBinding, control
        )
        observed = ResolvedObservation.model_validate(
            self.observations.load(baseline.observation_ref, op)
        )
        stored_observation = self.reads.parse(
            baseline.observation_ref,
            "observation/1",
            Observation,
            control,
            visibility="public",
        )
        if observed.record != stored_observation:
            raise OwnershipConflict(
                "Observation port returned a different initial record"
            )
        skill = self.reads.parse(
            skill_ref, "compact-skill/1", CompactSkill, control, visibility="public"
        )
        control.checkpoint()
        return CandidateFacts(
            equivalence_ref=equivalence_ref,
            skill_ref=skill_ref,
            equivalence=equivalence,
            source=source,
            context=context,
            baseline=baseline,
            task_binding=binding,
            observation=observed,
            skill=skill,
        )
