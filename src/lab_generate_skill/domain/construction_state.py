"""Pure construction history projection, scheduling and stable target selection.

No model, filesystem, attempt, authorization or send side effects. A next_action
describes outstanding work, never permission to repeat it. Registered model
calls/attempts stay pending until their own saved result arrives. Unknown calls
cannot produce another send action; unknown judgments cannot become negatives.
"""

from dataclasses import dataclass, field
from typing import Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from .construction import (
    AttemptCompleted,
    AttemptIntent,
    AttemptPlanned,
    AttemptResolved,
    CallCompleted,
    CallPlanned,
    CallUncertain,
    ConstructionAttemptResult,
    ConstructionCall,
    ConstructionPlan,
    ProgressEvent,
    SelectionCommitted,
    SelectionResult,
)
from .construction_inputs import GeneratedCandidate, RevisionResult
from .errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
    JournalCapacityExceeded,
)
from .validation import Contract, Identifier

_EVENT: TypeAdapter[ProgressEvent] = TypeAdapter(ProgressEvent)
_ATTEMPTS: TypeAdapter[tuple[ConstructionAttemptResult, ...]] = TypeAdapter(
    tuple[ConstructionAttemptResult, ...]
)


class ResolvedCandidate(Contract):
    schema_version: Literal["resolved-candidate/1"] = "resolved-candidate/1"
    call: ConstructionCall
    response: GeneratedCandidate | RevisionResult


class ConstructionAction(Contract):
    schema_version: Literal["construction-action/1"] = "construction-action/1"
    kind: Literal[
        "generate",
        "execute",
        "revise",
        "select",
        "await_response",
        "await_attempt",
        "blocked",
        "complete",
    ]
    candidate_slot: int | None = None
    resample_index: int | None = None
    request_id: Identifier | None = None
    attempt_id: Identifier | None = None


class ConstructionView(Contract):
    schema_version: Literal["construction-view/1"] = "construction-view/1"
    candidates: tuple[ResolvedCandidate, ...]
    attempts: tuple[ConstructionAttemptResult, ...]
    pending_call: ConstructionCall | None
    pending_attempt: AttemptIntent | None
    next_action: ConstructionAction
    selection: SelectionResult | None


def select_target(attempts: tuple[ConstructionAttemptResult, ...]) -> SelectionResult:
    """Stable earliest tie by actual environment returns; never score unknown."""
    attempts = _ATTEMPTS.validate_python(attempts, strict=True)
    if any(attempt.evaluation.status == "unknown" for attempt in attempts):
        raise InvalidTransition("Unknown attempt cannot be used for target selection")
    successes = [item for item in attempts if item.evaluation.status == "success"]
    if not successes:
        return SelectionResult(status="rejected")
    best = min(successes, key=lambda item: item.interactions)
    return SelectionResult(
        status="accepted",
        candidate_slot=best.intent.candidate_slot,
        attempt_id=best.intent.binding.attempt_id,
        skill_digest=best.intent.skill_digest,
    )


@dataclass
class _Projection:
    plan: ConstructionPlan
    candidates: list[ResolvedCandidate] = field(default_factory=list)
    attempts: list[ConstructionAttemptResult] = field(default_factory=list)
    requests: set[str] = field(default_factory=set)
    attempt_ids: set[str] = field(default_factory=set)
    pending_call: ConstructionCall | None = None
    pending_attempt: AttemptIntent | None = None
    retry: int = 0
    selection: SelectionResult | None = None

    def remaining_events(self) -> int:
        """Conservative slots for results and bounded normal method completion.

        Each future model call reserves plan/uncertain/result; each attempt
        reserves plan/unknown-result/resolution. Repeated unknown observations
        may use only surplus slots, never the remaining result/selection room.
        This is an event bound, not a promise of writable disk or bounded bytes.
        """
        action = self.action().kind
        if action == "complete":
            return 0
        if action == "select":
            return 1
        generators = max(0, (4 - min(4, len(self.candidates))) * 5 - self.retry)
        teachers = max(0, 7 - max(4, len(self.candidates)))
        calls = 3 * (generators + teachers) - int(self.pending_call is not None)
        attempts = 3 * (7 - len(self.attempts)) - int(self.pending_attempt is not None)
        unknown = int(
            any(item.evaluation.status == "unknown" for item in self.attempts)
        )
        return calls + attempts + unknown + 1

    def action(self) -> ConstructionAction:
        if self.selection is not None:
            return ConstructionAction(kind="complete")
        if self.pending_call is not None:
            return ConstructionAction(
                kind="await_response", request_id=self.pending_call.request_id
            )
        if self.pending_attempt is not None:
            return ConstructionAction(
                kind="await_attempt", attempt_id=self.pending_attempt.binding.attempt_id
            )
        if any(item.evaluation.status == "unknown" for item in self.attempts):
            return ConstructionAction(kind="blocked")
        if len(self.candidates) < 4:
            return ConstructionAction(
                kind="generate",
                candidate_slot=len(self.candidates),
                resample_index=self.retry,
            )
        if len(self.attempts) < len(self.candidates):
            return ConstructionAction(kind="execute", candidate_slot=len(self.attempts))
        if len(self.attempts) == 4:
            return ConstructionAction(kind="revise", candidate_slot=4, resample_index=0)
        if (
            any(item.evaluation.status == "success" for item in self.attempts)
            or len(self.attempts) == 7
        ):
            return ConstructionAction(kind="select")
        return ConstructionAction(
            kind="revise", candidate_slot=len(self.attempts), resample_index=0
        )

    def call_planned(self, event: CallPlanned, action: ConstructionAction) -> None:
        call = event.call
        if (
            action.kind not in ("generate", "revise")
            or call.candidate_slot != action.candidate_slot
            or call.resample_index != action.resample_index
        ):
            raise InvalidTransition("Call is outside the next frozen schedule slot")
        role = "generator" if action.kind == "generate" else "teacher"
        if call.role != role or call.request_id in self.requests:
            raise OwnershipConflict("Call role or request identity reused")
        seed, temperature = (
            self.plan.method.generator_sampling(
                call.candidate_slot, call.resample_index
            )
            if role == "generator"
            else (self.plan.method.teacher_seed(call.candidate_slot - 3), None)
        )
        if (call.seed, call.temperature) != (seed, temperature):
            raise ValueError("Call sampling differs from the frozen method")
        model = next(item for item in self.plan.models if item.role == role)
        if (
            call.model_binding_ref != model.model_binding_ref
            or call.base_parameters_ref != model.parameters_ref
        ):
            raise OwnershipConflict("Call model binding changed")
        self.requests.add(call.request_id)
        self.pending_call = call

    def call_completed(self, event: CallCompleted) -> None:
        call = self.pending_call
        response = event.response
        if call is None:
            raise InvalidTransition("No registered call to complete")
        if (response.request_id, response.input_sha256, response.parameters_sha256) != (
            call.request_id,
            call.input_ref.sha256,
            call.parameters_ref.sha256,
        ):
            raise OwnershipConflict("Response does not bind the registered call")
        if isinstance(response, GeneratedCandidate) != (call.role == "generator"):
            raise ValueError("Wrong response role")
        duplicate = response.skill.content_digest in {
            item.response.skill.content_digest for item in self.candidates
        }
        if (
            call.role == "generator"
            and duplicate
            and self.retry < self.plan.method.duplicate_resamples
        ):
            self.retry += 1
        else:
            self.candidates.append(ResolvedCandidate(call=call, response=response))
            self.retry = 0
        self.pending_call = None

    def attempt_planned(
        self, event: AttemptPlanned, action: ConstructionAction
    ) -> None:
        intent = event.intent
        if action.kind != "execute" or intent.candidate_slot != action.candidate_slot:
            raise InvalidTransition("Attempt is outside the next candidate slot")
        if intent.binding.attempt_id in self.attempt_ids:
            raise OwnershipConflict("Attempt ID reused")
        if (
            intent.binding.run != self.plan.run
            or intent.binding.task != self.plan.task.identity
            or intent.binding.claim_ref != self.plan.claim_ref
            or intent.public_context_ref != self.plan.public_context_ref
        ):
            raise OwnershipConflict("Attempt task/claim/baseline binding changed")
        if (
            intent.skill_digest
            != self.candidates[intent.candidate_slot].response.skill.content_digest
        ):
            raise OwnershipConflict("Attempt skill changed")
        self.attempt_ids.add(intent.binding.attempt_id)
        self.pending_attempt = intent

    def check_result(self, result: ConstructionAttemptResult) -> None:
        if (
            result.generations > self.plan.max_actor_generations
            or result.interactions > self.plan.max_interactions
        ):
            raise ValueError("Attempt exceeded frozen execution bounds")

    def apply(self, event: ProgressEvent) -> None:
        action = self.action()
        if action.kind == "complete":
            raise InvalidTransition("Construction is sealed")
        if isinstance(event, CallPlanned):
            self.call_planned(event, action)
        elif isinstance(event, CallCompleted):
            self.call_completed(event)
        elif isinstance(event, CallUncertain):
            if (
                self.pending_call is None
                or event.request_id != self.pending_call.request_id
            ):
                raise OwnershipConflict("Uncertainty belongs to an existing call")
        elif isinstance(event, AttemptPlanned):
            self.attempt_planned(event, action)
        elif isinstance(event, AttemptCompleted):
            if (
                self.pending_attempt is None
                or event.result.intent != self.pending_attempt
            ):
                raise OwnershipConflict("Result has no matching pending attempt")
            self.check_result(event.result)
            self.attempts.append(event.result)
            self.pending_attempt = None
        elif isinstance(event, AttemptResolved):
            if action.kind != "blocked" or not self.attempts:
                raise InvalidTransition("Only an unknown judgment can be resolved")
            previous = self.attempts[-1]
            current = event.result
            if (
                previous.evaluation.status != "unknown"
                or current.evaluation.supersedes != previous.evaluation_ref
                or current.evaluation_ref == previous.evaluation_ref
            ):
                raise OwnershipConflict(
                    "Resolution must supersede the unknown judgment with new evidence"
                )
            if current.model_dump(
                exclude={"evaluation", "evaluation_ref"}
            ) != previous.model_dump(exclude={"evaluation", "evaluation_ref"}):
                raise OwnershipConflict("Resolution cannot rewrite execution facts")
            self.check_result(current)
            self.attempts[-1] = current
        elif isinstance(event, SelectionCommitted):
            if action.kind != "select" or event.selection != select_target(
                tuple(self.attempts)
            ):
                raise InvalidTransition(
                    "Selection differs from the complete method outcome"
                )
            self.selection = event.selection

    def view(self) -> ConstructionView:
        return ConstructionView(
            candidates=tuple(self.candidates),
            attempts=tuple(self.attempts),
            pending_call=self.pending_call,
            pending_attempt=self.pending_attempt,
            next_action=self.action(),
            selection=self.selection,
        )


class ConstructionProgress(Contract):
    schema_version: Literal["construction-progress/1"] = "construction-progress/1"
    plan: ConstructionPlan
    events: tuple[ProgressEvent, ...] = Field(default=(), max_length=256)

    @property
    def revision(self) -> int:
        return len(self.events) - 1

    def _project(
        self, *, capacity: bool = False
    ) -> tuple[_Projection, tuple[tuple[int, int], ...]]:
        projection = _Projection(self.plan)
        seen: set[str] = set()
        usage: list[tuple[int, int]] = []
        for index, event in enumerate(self.events, start=1):
            op = event.operation
            if (op.run_id, op.owner_id) != (
                self.plan.run.owner.run_id,
                self.plan.run.owner.owner_id,
            ) or op.attempt_id is not None:
                raise OwnershipConflict("Construction operation scope changed")
            if op.operation_id in seen:
                raise OwnershipConflict("Construction operation ID reused")
            if op.mode != "execute" and not isinstance(
                event, (CallCompleted, CallUncertain, AttemptCompleted, AttemptResolved)
            ):
                raise InvalidTransition(
                    "Cleanup may reconcile facts but cannot schedule new work"
                )
            seen.add(op.operation_id)
            projection.apply(event)
            if index + projection.remaining_events() > 256:
                raise JournalCapacityExceeded(
                    "Construction history must retain result and selection slots"
                )
            if capacity:
                usage.append(
                    (
                        len(event.model_dump_json().encode()),
                        projection.remaining_events(),
                    )
                )
        return projection, tuple(usage)

    def project(self) -> ConstructionView:
        return self._project()[0].view()

    def remaining_event_slots(self) -> int:
        """Conservative completion reserve for the current method state."""
        return self._project()[0].remaining_events()

    def capacity_usage(self) -> tuple[tuple[int, int], ...]:
        """For each committed prefix: new event UTF-8 bytes and remaining slots."""
        return self._project(capacity=True)[1]

    @model_validator(mode="after")
    def valid_history(self) -> Self:
        self.project()
        return self


def append_construction_event(
    progress: ConstructionProgress, event: ProgressEvent, expected_revision: int
) -> ConstructionProgress:
    """Pure compare/replay; caller must use an atomic persistent transaction."""
    progress = ConstructionProgress.model_validate(progress)
    if type(expected_revision) is not int or expected_revision < -1:
        raise ValueError("Invalid construction revision")
    event = _EVENT.validate_python(event, strict=True)
    for prior in progress.events:
        if prior.operation.operation_id == event.operation.operation_id:
            if prior != event:
                raise OwnershipConflict(
                    "Operation already binds different construction facts"
                )
            return progress
    if progress.revision != expected_revision:
        raise RevisionConflict("Construction revision changed")
    return ConstructionProgress(plan=progress.plan, events=(*progress.events, event))
