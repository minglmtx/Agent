"""Explicit same-snapshot read port; registration and current authority required."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation_read import (
    ObservationReadRequest,
    ObservationReadPayload,
    PublicObservationSnapshot,
)
from lab_generate_skill.domain.observation_read_progress import ObservationReadProgress
from lab_generate_skill.domain.observation_read_return import ReturnedObservationRead
from lab_generate_skill.domain.context_budget import CountedContextInput
from lab_generate_skill.domain.actor_observation_view import ActorObservationView
from .lifecycle import OperationControl


@runtime_checkable
class ObservationReads(Protocol):
    def read(
        self,
        request: ObservationReadRequest,
        operation: OperationContext,
        *,
        progress: ObservationReadProgress,
        control: OperationControl,
        retention_control: OperationControl | None = None,
    ) -> ReturnedObservationRead:
        """Publish exact public ranges; no browser step or implicit recapture."""
        ...


@runtime_checkable
class ObservationProposalChecks(Protocol):
    def check_proposal(
        self,
        request: ObservationReadRequest,
        view: ActorObservationView,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        """Check current retained inputs before ReadPlanned; never dispatch or spend."""
        ...


class ObservationReadAuthority(Protocol):
    def require_current(
        self,
        snapshot: PublicObservationSnapshot,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        """Original live task/claim/browser/trace/storage gates, every read."""
        ...


class ObservationBodyCounts(Protocol):
    def measure_body(
        self,
        payload: ObservationReadPayload,
        body: str,
        operation: OperationContext,
        *,
        control: OperationControl,
        retention_control: OperationControl | None = None,
    ) -> CountedContextInput:
        """Exact original resident tokenizer; no inference or fragment sum."""
        ...
