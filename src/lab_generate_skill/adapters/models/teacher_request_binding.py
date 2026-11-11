"""Bind actual Teacher sampling/output parameters to the frozen original plan.

This pure adapter check grants no provider capability, token-count bound or fee
permission. Generic OpenRouter requests keep their existing interface. Teacher
must explicitly retain the original method seed and the reserved output limit.
"""

from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.adapters.processes.wire_json import json_object


def verify_teacher_wire_parameters(raw: bytes, plan: TeacherRevisionPlan) -> None:
    if (
        type(raw) is not bytes
        or not 0 < len(raw) <= plan.send.limits.max_parameters_bytes
    ):
        raise ValueError("Complete bounded original Teacher parameter bytes required")
    parameters = json_object(raw)
    seed = parameters.get("seed")
    maximum = parameters.get("max_tokens")
    if type(seed) is not int or seed != plan.revision.seed:
        raise OwnershipConflict(
            "Teacher wire must retain its exact original method seed"
        )
    if type(maximum) is not int or maximum != plan.preparation.profile.output_reserve:
        raise EvidenceIntegrityError(
            "Teacher actual max_tokens must equal its frozen output reservation"
        )
