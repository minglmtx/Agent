"""Original published initialization into candidate and Actor admission.

The one owned task carries immutable inputs; the original state/context authority
is invoked anew at each admission. Standalone readers keep their full graph path.
"""

from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.actor_admission import CandidateFacts
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes


def initialized_candidate_inputs(
    initial: RecordedTaskInitialization,
    equivalence_ref: EvidenceRef,
    skill_ref: EvidenceRef,
    operation: OperationContext,
    control: OperationControl,
) -> CandidateFacts:
    held, s = initial.inputs, initial.state
    if held is None:
        raise OwnershipConflict("Original owned task input scope required")
    held.check(operation, control)
    if (
        s.phase != "initialized"
        or held.equivalence is None
        or s.result is None
        or s.equivalence is None
        or s.baseline is None
        or s.baseline_ref is None
        or held.initial is None
        or s.result.equivalence_ref != equivalence_ref
        or initial.plan.skill_ref != skill_ref
    ):
        raise OwnershipConflict(
            "Original published initialization bodies missing or changed"
        )
    reference, inputs, dependencies = held.equivalence
    if (
        reference != equivalence_ref
        or reference != s.equivalence_ref
        or inputs.candidate_ref != s.baseline_ref
        or inputs.candidate != s.baseline
        or inputs.candidate_inputs != s.baseline_inputs
        or held.initial.selection != s.selection
        or held.initial.observation.record != inputs.candidate_inputs.observation
    ):
        raise OwnershipConflict(
            "Admission changed original published initialization inputs"
        )
    require_complete_bytes(s.baseline_ref, s.baseline.model_dump_json().encode())
    require_complete_bytes(reference, s.equivalence.model_dump_json().encode())
    skill = s.result.actor.skill
    require_complete_bytes(skill_ref, skill.model_dump_json().encode())
    initial.contexts.facts.verify_equivalence_inputs(
        inputs, s.equivalence, operation, control, dependencies=dependencies
    )
    control.checkpoint()
    return CandidateFacts(
        equivalence_ref=reference,
        skill_ref=skill_ref,
        equivalence=s.equivalence,
        source=inputs.source,
        context=inputs.source_inputs.context,
        baseline=s.baseline,
        task_binding=inputs.candidate_inputs.binding,
        observation=held.initial.observation,
        skill=skill,
    )
