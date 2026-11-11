"""Teacher consumes only its approved projection; no raw dependency container."""

from typing import Protocol

from lab_generate_skill.domain.construction_inputs import RevisionInput, RevisionResult
from lab_generate_skill.domain.lifecycle import OperationContext


class Teacher(Protocol):
    def revise(
        self, request: RevisionInput, op: OperationContext
    ) -> RevisionResult: ...
