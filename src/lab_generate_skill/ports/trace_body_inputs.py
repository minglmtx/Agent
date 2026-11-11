"""Same-task event evidence handed to original trace sealing, never permission."""

from contextlib import AbstractContextManager
from collections.abc import Mapping
from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_events import TraceProgressEvent
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from .evidence import EvidenceReader
from .lifecycle import OperationControl


class TraceBodyScope(Protocol):
    @property
    def task_identity(self) -> TaskIdentity: ...
    def check(self, op: OperationContext, control: OperationControl) -> None: ...


@runtime_checkable
class TraceEventInputReads(Protocol):
    def event_inputs(
        self,
        before: TraceSnapshot,
        event: TraceProgressEvent,
        op: OperationContext,
        original: EvidenceReader,
        control: OperationControl,
    ) -> AbstractContextManager[EvidenceReader]: ...


@runtime_checkable
class TraceSealingInputReads(Protocol):
    def sealing_inputs(
        self,
        trace: InteractionTrace,
        op: OperationContext,
        original: EvidenceReader,
        control: OperationControl,
    ) -> AbstractContextManager[EvidenceReader]: ...


class TraceBodyInputs(TraceEventInputReads, TraceSealingInputReads, Protocol):
    @property
    def statistics(self) -> Mapping[str, int]: ...
    def clear(self) -> None: ...


@runtime_checkable
class VerifiedTraceReferenceReads(Protocol):
    def verify_trace_reference(
        self, reference: EvidenceRef, control: OperationControl
    ) -> bool:
        """A complete same-task event read, never a current permission verdict."""
        ...


@runtime_checkable
class TraceObservationInputReads(Protocol):
    def observation_inputs(
        self, reference: EvidenceRef, control: OperationControl
    ) -> ResolvedObservation | None: ...
    def observed_inputs(
        self,
        reference: EvidenceRef,
        observation: ResolvedObservation,
        control: OperationControl,
    ) -> None: ...
