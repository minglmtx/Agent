"""Store/read recorded execution; never interpret trace publication as a permit.

Authority verifies original writer/attempt registration and limits, model-call
provenance, action protocol/name/permissions, actual step returns and chronology.
No default authority. Unknown records remain diagnostic, never task failures.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.trace import InteractionTrace
from .lifecycle import OperationControl


@runtime_checkable
class InitialTraceObservationReads(Protocol):
    def read_initial(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> ResolvedObservation | None:
        """Same-task verified initial body; current owner/storage checked anew.

        No later observation or independent invocation inherits this body.
        Unconfigured consumers return None and retain complete reads.
        """
        ...


class TraceAuthority(Protocol):
    def verify(
        self,
        trace: InteractionTrace,
        observations: tuple[ResolvedObservation, ...],
        op: OperationContext,
    ) -> None: ...


class TraceRecords(Protocol):
    def publish(self, trace: InteractionTrace, op: OperationContext) -> EvidenceRef: ...
    def load(self, ref: EvidenceRef, op: OperationContext) -> InteractionTrace: ...
