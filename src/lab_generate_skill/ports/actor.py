"""Role projection and attempt orchestration; none grants model/browser permission."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.actor_generation import ActorGeneration, ActorDecision
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorPrompt
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from .lifecycle import OperationControl
from .evidence import EvidenceReader


class ActorProjection(Protocol):
    def __call__(self, turn: ActorPublicTurn) -> ActorPrompt: ...


class ActorDecisions(Protocol):
    def decide(
        self, generation: ActorGeneration, task: PublicTask, operation: OperationContext
    ) -> ActorDecision: ...


@runtime_checkable
class ActorRejectedInputReads(Protocol):
    def rejected_inputs(
        self,
        generation: ActorGeneration,
        decision: ActorDecision,
        control: OperationControl,
    ) -> EvidenceReader:
        """Only the just-confirmed rejection's current immutable bodies."""
        ...


class ActorRunAuthority(Protocol):
    def verify(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        """Read-only live gate before each new generation.

        Verify actual run/claim/writer, ready original baseline (and candidate
        equivalence where required), exact public task/skill, full AX provenance,
        method parameters/limits, original acquired model/browser and exclusive
        state access. This does not substitute the model or browser's dispatch
        authority. No default, action, request resend or reset is permitted here.
        """
        ...


class ActorRunner(Protocol):
    def run(self, request: ActorRunRequest) -> TraceSnapshot:
        """Consume a fresh trace and initialized session; return a sealed trace.

        Never start/reset/close a website or model. Surrounding task lifecycle
        owns capture/closure/restoration even if this call raises with pending
        original work. No takeover or resumption by invoking this method again.
        """
        ...
