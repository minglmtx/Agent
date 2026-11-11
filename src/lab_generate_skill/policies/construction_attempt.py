"""Derive only the original ready candidate intent; no allocation or execution."""

from pydantic import TypeAdapter
from lab_generate_skill.domain.construction import AttemptIntent, AttemptPlanned
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.validation import Identifier

_ID = TypeAdapter(Identifier)


def original_attempt_intent(
    progress: ConstructionProgress, attempt_id: str
) -> AttemptIntent:
    progress = ConstructionProgress.model_validate(progress)
    attempt_id = _ID.validate_python(attempt_id, strict=True)
    view = progress.project()
    slot = view.next_action.candidate_slot
    if view.next_action.kind != "execute" or slot is None:
        raise InvalidTransition(
            "Only the original ready Actor slot has a new intent; pending/unknown cannot renew"
        )
    if any(
        isinstance(event, AttemptPlanned)
        and event.intent.binding.attempt_id == attempt_id
        for event in progress.events
    ):
        raise OwnershipConflict("Original registered attempt identity cannot be reused")
    return AttemptIntent(
        binding=AttemptBinding(
            run=progress.plan.run,
            attempt_id=attempt_id,
            task=progress.plan.task.identity,
            claim_ref=progress.plan.claim_ref,
        ),
        candidate_slot=slot,
        skill_digest=view.candidates[slot].response.skill.content_digest,
        public_context_ref=progress.plan.public_context_ref,
    )
