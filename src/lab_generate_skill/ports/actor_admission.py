"""Read-only admission dependencies; no browser, model or dispatch defaults.

Authority must verify live claim/writer, pending ownership, registered resources,
unchanged initial state/exclusive lease and permitted execution scope. It must
not invoke models, mutate environments or grant a reusable dispatch token.
"""

from typing import Protocol
from lab_generate_skill.domain.actor_admission import (
    CandidateFacts,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext


class CandidateInputs(Protocol):
    def load(
        self, equivalence_ref: EvidenceRef, skill_ref: EvidenceRef, op: OperationContext
    ) -> CandidateFacts: ...
