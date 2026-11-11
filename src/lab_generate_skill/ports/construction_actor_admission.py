"""Construction-only candidate/writer grant, separate from common initial fact reads."""

from typing import Protocol
from lab_generate_skill.domain.actor_admission import (
    ActorAdmissionRequest,
    CandidateFacts,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.run_journal import RunSnapshot


class ActorAdmissionAuthority(Protocol):
    def verify(
        self,
        request: ActorAdmissionRequest,
        facts: CandidateFacts,
        construction: ConstructionProgress,
        run: RunSnapshot,
    ) -> None: ...
