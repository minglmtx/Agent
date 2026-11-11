"""Record the first Actor intent, invoke once, then persist the actual outcome.

No prompt rendering, parsing, website access or automatic reconciliation. A
pending intent is never a new invocation opportunity. Result acknowledgement
uses its own bounded cleanup operation; a lost acknowledgement retains both the
original returned value and the exact observed event for read-only reconciliation.
The enclosing attempt remains responsible for resource closure and isolation.
"""

from typing import Literal
from datetime import timedelta
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.trace_events import GenerationObserved
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.actor_model import ActorModel
from lab_generate_skill.ports.lifecycle import OperationControls, Clock
from .actor_generation_control import generation_preparation_control
from lab_generate_skill.ports.trace_journal import TraceJournal

Phase = Literal[
    "preflight",
    "commit_intent",
    "before_generate",
    "generate",
    "validate_return",
    "commit_result",
]


class ActorDispatchFailure(RuntimeError):
    reason_code = "ACTOR_GENERATION_UNCONFIRMED"

    def __init__(
        self,
        request: ActorDispatch,
        phase: Phase,
        primary: BaseException,
        acknowledged: TraceSnapshot | None,
        returned: object,
        observed: GenerationObserved | None,
    ) -> None:
        self.request, self.phase, self.primary = request, phase, primary
        self.acknowledged, self.returned, self.observed = (
            acknowledged,
            returned,
            observed,
        )
        super().__init__(
            f"Actor generation stopped in {phase}; preserve original facts and do not resend"
        )


def execute_actor_generation(
    request: ActorDispatch,
    journal: TraceJournal,
    model: ActorModel,
    controls: OperationControls,
    *,
    clock: Clock | None = None,
) -> TraceSnapshot:
    request = ActorDispatch.model_validate(request)
    intent = request.intent.intent
    phase: Phase = "preflight"
    acknowledged: TraceSnapshot | None = None
    returned: object = None
    observed: GenerationObserved | None = None
    try:
        if intent.execution_window is not None and clock is None:
            raise ValueError("Selected generation windows require the original clock")
        control = generation_preparation_control(
            intent.operation, intent.execution_window, controls.bind(intent.operation)
        )
        control.checkpoint()
        model.validate(intent, control=control)
        control.checkpoint()
        phase = "commit_intent"
        acknowledged = TraceSnapshot.model_validate(
            journal.append(
                request.intent, request.expected_revision, request.intent.operation
            )
        )
        if (
            acknowledged.revision != request.expected_revision + 1
            or acknowledged.events[-1] != request.intent
            or acknowledged.project().intent != intent
        ):
            raise OwnershipConflict(
                "Journal did not acknowledge this exact first generation"
            )
        phase = "before_generate"
        control.checkpoint()
        phase = "generate"
        returned = model.generate(intent, control=control)
        phase = "validate_return"
        generation = ActorGeneration.model_validate(returned)
        if not intent.matches(generation):
            raise OwnershipConflict("Actor return changed original generation intent")
        result_operation = request.result_operation
        if intent.execution_window is not None:
            assert clock is not None
            seconds = (
                result_operation.deadline - intent.operation.deadline
            ).total_seconds()
            seconds -= intent.execution_window.budgets.retention_seconds or 0
            if not 0 < seconds <= 60:
                raise ValueError(
                    "Selected call result must retain bounded original cleanup"
                )
            # This result operation has not been bound/registered yet. Shorten
            # its fixed ceiling to the actual return; never extend an operation.
            result_operation = result_operation.model_copy(
                update={
                    "deadline": min(
                        result_operation.deadline,
                        clock.utcnow() + timedelta(seconds=seconds),
                    )
                }
            )
        observed = GenerationObserved(operation=result_operation, generation=generation)
        phase = "commit_result"
        after = TraceSnapshot.model_validate(
            journal.append(observed, acknowledged.revision, result_operation)
        )
        if (
            after.plan != acknowledged.plan
            or after.creation_operation != acknowledged.creation_operation
            or after.events != (*acknowledged.events, observed)
        ):
            raise OwnershipConflict(
                "Journal did not confirm the original Actor outcome"
            )
        return after
    except BaseException as error:
        raise ActorDispatchFailure(
            request, phase, error, acknowledged, returned, observed
        ) from error
