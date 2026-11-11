"""Atomic construction history; no model, dispatch or attempt retry on read.

Create freezes the complete plan; append compares global revision under one
transaction and preserves exact operation replay. Verify referenced input,
response, attempt and evaluation bytes before publishing a new event. A lost
commit acknowledgement requires read/precise replay, never external reexecution.
The concrete adapter must define capacity/closure and crash behavior separately.
Append normally uses the event operation. A fresh run-level cleanup operation
with parent_operation_id equal to the original event operation may reconcile an
existing fact after its deadline; it preserves the original event bytes and may
not register new calls, attempts or selections. Exact stored replay is read-only.
"""

from typing import Protocol

from lab_generate_skill.domain.construction import ConstructionPlan, ProgressEvent
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.construction_preparation import PublishedConstructionStep
from lab_generate_skill.ports.lifecycle import OperationControl


class ConstructionJournal(Protocol):
    def create(
        self, plan: ConstructionPlan, op: OperationContext
    ) -> ConstructionProgress: ...
    def read(self, op: OperationContext) -> ConstructionProgress: ...
    def append(
        self, event: ProgressEvent, expected_revision: int, op: OperationContext
    ) -> ConstructionProgress: ...


class ConstructionSourceProof(Protocol):
    """Reverify the existing full frozen source graph and its required authority.

    This is a selective read on the original construction, not a second journal
    or a dispatch permission. Ordinary historical read/replay stays available
    without reauthorizing new work; this method never mutates or retries it.
    """

    def verify_source(self, op: OperationContext) -> ConstructionProgress: ...


class ConstructionAuthority(Protocol):
    """Mandatory trusted, local semantic checks under the construction lock.

    Check real claim/writer and run admission, qualified context/retrieval,
    request parameters and provider result parsing, attempt closure/counters,
    and review provenance. Matching refs or a typed result is not authority.
    Hooks must not call models, mutate resources, submit jobs or retry I/O.
    Test fixtures must never be production defaults.
    """

    def verify_plan(self, plan: ConstructionPlan, op: OperationContext) -> None: ...

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None: ...


class ConstructionSteps(Protocol):
    def load(
        self,
        reference: EvidenceRef,
        run: RunBinding,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> PublishedConstructionStep:
        """Read exact saved step, without scheduling/rebinding original work."""
        ...
