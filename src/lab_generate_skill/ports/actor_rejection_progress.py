"""Read actual persisted rejection facts without granting a new Actor request."""

from typing import Protocol
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorInvalidProposalProgress,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from .lifecycle import OperationControl
from .evidence import EvidenceReader


class ActorRejectionProgress(Protocol):
    def derive(
        self,
        snapshot: TraceSnapshot,
        current_observation: EvidenceRef,
        policy: ObservationReadPolicy,
        *,
        control: OperationControl,
        inputs: EvidenceReader | None = None,
    ) -> ActorInvalidProposalProgress: ...
