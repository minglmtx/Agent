"""Typed original leaves; private records are never dumped into native messages."""

from dataclasses import dataclass
from .actor_prompt import ActorPrompt
from .actor_response import ActorTextCompletion, ActorParseFailure
from .actor_run import ActorRunRequest
from .browser_session import BrowserReadout
from .evaluation import Evaluation
from .observation import ResolvedObservation
from .teacher_attempt import TeacherAttemptInput
from .trace import InteractionTrace, TraceTurn
from .observation_read import ObservationReadPayload


@dataclass(frozen=True)
class TeacherActorTurn:
    trace_turn: TraceTurn
    before: ResolvedObservation
    recorded_input: ActorPrompt
    completion: ActorTextCompletion | None
    parse_failure: ActorParseFailure | None
    returned: BrowserReadout | None
    after: ResolvedObservation | None
    reading: ObservationReadPayload | None = None


@dataclass(frozen=True)
class TeacherActorMaterial:
    original: TeacherAttemptInput
    request: ActorRunRequest
    trace: InteractionTrace
    evaluation: Evaluation
    initial: ResolvedObservation
    turns: tuple[TeacherActorTurn, ...]
