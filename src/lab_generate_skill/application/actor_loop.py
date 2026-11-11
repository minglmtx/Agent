"""Fresh-attempt Actor loop over registered model/browser ports and one trace.

Starts neither resource nor browser session. Every new effect uses its existing
first-intent dispatcher. A confirmed terminal browser return seals 'finished',
which is not task success. Unknown pending effects stay unsealed and never retry.
Outer task lifecycle must always capture, close and restore its original state.
"""

from lab_generate_skill.ports.actor_context import ActorContextInputLifetime

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.actor_generation import ActorDecision
from lab_generate_skill.domain.actor_execution_window import ActorGenerationWindow
from .actor_round_preparation import select_round_preparation
from .actor_rejection_progress import check_repeated_invalid_proposals
from lab_generate_skill.domain.actor_budget_stop import ActorRoundBudgetStopped
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.actor_context import ActorPreparedInput
from lab_generate_skill.domain.browser_dispatch import BrowserDispatch
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.lifecycle import AllocationToken, OperationContext
from lab_generate_skill.domain.trace_events import (
    GenerationIntent,
    GenerationPlanned,
    DecisionRejected,
    ActionPlanned,
    TraceSealed,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.actor import (
    ActorProjection,
    ActorDecisions,
    ActorRejectedInputReads,
    ActorRunAuthority,
)
from lab_generate_skill.ports.actor_model import ActorModel
from lab_generate_skill.ports.actor_context import ActorInputPreparation
from lab_generate_skill.ports.browser import BrowserActions
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.ports.trace_journal import TraceJournal
from .actor_generation import ActorDispatchFailure, execute_actor_generation
from .browser_action import execute_browser_action
from .actor_loop_inputs import prepare_turn, put_actor_fact, actor_operation_id
from .observation_read import execute_observation_read
from lab_generate_skill.domain.observation_read_dispatch import ObservationReadDispatch
from lab_generate_skill.domain.trace_events import ReadPlanned
from lab_generate_skill.ports.observation_reads import ObservationReads


@dataclass(frozen=True)
class ActorLoopDeps:
    journal: TraceJournal
    evidence: EvidenceStore
    observations: Observations
    model: ActorModel
    browser: BrowserActions
    decisions: ActorDecisions
    project: ActorProjection
    authority: ActorRunAuthority
    controls: OperationControls
    clock: Clock
    context: ActorInputPreparation | None = None
    readings: ObservationReads | None = None


class ActorLoopFailure(RuntimeError):
    reason_code = "ACTOR_LOOP_STOPPED"

    def __init__(
        self,
        primary: BaseException,
        request_ref: EvidenceRef | None,
        snapshot: TraceSnapshot | None,
        cleanup_errors: tuple[BaseException, ...],
    ) -> None:
        self.primary, self.request_ref, self.snapshot, self.cleanup_errors = (
            primary,
            request_ref,
            snapshot,
            cleanup_errors,
        )
        super().__init__(
            "Actor loop stopped; preserve original trace and close/restore resources without replay"
        )


class RecordedActorRunner:
    def __init__(self, deps: ActorLoopDeps) -> None:
        self.deps = deps

    def run(self, request: ActorRunRequest) -> TraceSnapshot:
        request = ActorRunRequest.model_validate(request)
        d = self.deps
        snapshot: TraceSnapshot | None = None
        request_ref: EvidenceRef | None = None
        seal_attempted = False
        preparation_active = False
        preparation_index = 0

        def identity(label: str) -> str:
            return actor_operation_id(request.operation.operation_id, label)

        def execute(
            label: str, token: AllocationToken | None = None, seconds: int | None = None
        ) -> OperationContext:
            values: dict[str, object] = {"operation_id": identity(label)}
            if token is not None:
                values.update(
                    allocation_id=token.allocation_id, recovery_ref=token.recovery_ref
                )
            if seconds is not None:
                values["deadline"] = min(
                    request.operation.deadline,
                    d.clock.utcnow() + timedelta(seconds=seconds),
                )
            return OperationContext.model_validate(
                {**request.operation.model_dump(), **values}
            )

        def cleanup(
            label: str,
            parent: OperationContext,
            *,
            after_deadline: bool = False,
            seconds: int | None = None,
        ) -> OperationContext:
            # Dispatch requests are frozen before invocation. Their independent
            # result window extends from the bounded execution deadline, not
            # from time spent preparing the request before a long model call.
            return parent.cleanup(
                identity(label),
                now=parent.deadline if after_deadline else d.clock.utcnow(),
                seconds=request.cleanup_seconds if seconds is None else seconds,
            )

        def seal(before: TraceSnapshot, reason: str, label: str) -> TraceSnapshot:
            nonlocal seal_attempted
            assert request_ref is not None
            seal_attempted = True
            op = cleanup(label, request.operation)
            view = before.project()
            fact = ActorStop.model_validate(
                dict(
                    request_ref=request_ref,
                    scope=request.scope,
                    reason=reason,
                    generations=len(view.turns) + int(view.generation is not None),
                    interactions=view.interactions,
                    final_observation_ref=view.current_observation(before.plan),
                )
            )
            ref = put_actor_fact(fact, d.evidence, d.controls.bind(op))
            event = TraceSealed.model_validate(
                dict(operation=op, stop_reason=reason, stop_evidence_ref=ref)
            )
            after = TraceSnapshot.model_validate(
                d.journal.append(event, before.revision, op)
            )
            if (
                after.plan != before.plan
                or after.creation_operation != before.creation_operation
                or after.events != (*before.events, event)
            ):
                raise OwnershipConflict("Actor seal did not confirm the original trace")
            return after

        try:
            if (request.schema_version == "actor-run-request/2") != (
                d.context is not None
            ):
                raise OwnershipConflict(
                    "Actor context version/dependency mismatch; no silent fallback"
                )
            control = d.controls.bind(request.operation)
            control.checkpoint()
            first_preparation = (
                select_round_preparation(request, 0, d.controls, d.clock)
                if request.generation_budgets is not None
                else None
            )
            preparation_active = first_preparation is not None
            setup_control = (
                control if first_preparation is None else first_preparation.control
            )
            initial_read = execute("initial-read")
            if first_preparation is not None:
                initial_read = first_preparation.bound(initial_read)
            snapshot = TraceSnapshot.model_validate(d.journal.read(initial_read))
            if (
                snapshot.events
                or snapshot.plan.scope != request.scope
                or snapshot.plan.initial_observation_ref
                != request.initial_observation_ref
                or len(request.parameters_refs) != snapshot.plan.max_generations
            ):
                raise OwnershipConflict(
                    "Actor requires its fresh original trace, observation and frozen generation budget"
                )
            d.authority.verify(request, snapshot, setup_control)
            setup_control.checkpoint()
            initial_operation = execute("initial-observation")
            if first_preparation is not None:
                initial_operation = first_preparation.bound(initial_operation)
            initial = d.observations.load(
                request.initial_observation_ref, initial_operation
            )
            initial.record.check_initial(request.scope.task, request.scope.context_id)
            if initial.record.attempt_id != request.scope.attempt_id:
                raise OwnershipConflict(
                    "Actor initial observation changed original attempt"
                )
            request_ref = put_actor_fact(request, d.evidence, setup_control)
            preparation_active = False
            while True:
                view = snapshot.project()
                if view.halted:
                    last = view.turns[-1]
                    reason = (
                        "uncertain"
                        if last.generation.status == "uncertain"
                        or (
                            last.reading is not None
                            and last.reading.outcome == "uncertain"
                        )
                        else "error"
                    )
                    if (
                        last.interaction is not None
                        and last.interaction.result is not None
                        and last.interaction.result.terminal
                    ):
                        reason = "finished"
                    return seal(snapshot, reason, "seal")
                if len(view.turns) >= snapshot.plan.max_generations:
                    return seal(snapshot, "generation_limit", "seal")
                if view.interactions >= snapshot.plan.max_interactions:
                    return seal(snapshot, "interaction_limit", "seal")
                control.checkpoint()
                index = len(view.turns)
                prefix = f"turn-{index}"
                selected = request.generation_budgets
                preparation_index = index
                preparation = (
                    first_preparation
                    if index == 0 and first_preparation is not None
                    else select_round_preparation(request, index, d.controls, d.clock)
                )
                first_preparation = None
                gen_op, window, gen_control = (
                    preparation.operation,
                    preparation.window,
                    preparation.control,
                )
                preparation_active = window is not None
                # Dynamic authority is part of this round's bounded preparation.
                # Its original request/snapshot identity and actual send gate stay mandatory.
                d.authority.verify(request, snapshot, gen_control)
                gen_control.checkpoint()
                prepared_ref = None
                if d.context is None:
                    prompt = prepare_turn(
                        request,
                        snapshot,
                        gen_op,
                        gen_control,
                        d.evidence,
                        d.observations,
                        d.project,
                    )
                    input_ref = put_actor_fact(prompt, d.evidence, gen_control)
                else:
                    prepared = ActorPreparedInput.model_validate(
                        d.context.prepare(
                            request,
                            snapshot,
                            gen_op,
                            identity(prefix + "-request"),
                            control=gen_control,
                        )
                    )
                    input_ref, prepared_ref = (
                        prepared.input_ref,
                        prepared.preparation_ref,
                    )
                intent_data: dict[str, object] = dict(
                    scope=request.scope,
                    operation=gen_op,
                    generation_id=identity(prefix + "-generation"),
                    request_id=identity(prefix + "-request"),
                    before_observation_ref=view.current_observation(snapshot.plan),
                    input_ref=input_ref,
                    parameters_ref=request.parameters_refs[index],
                )
                if window is not None:
                    intent_data["execution_window"] = window
                if prepared_ref is not None:
                    intent_data.update(
                        schema_version="actor-generation-intent/2",
                        context_preparation_ref=prepared_ref,
                    )
                intent = GenerationIntent.model_validate(intent_data)
                intent_operation = execute(prefix + "-intent")
                if window is not None:
                    intent_operation = intent_operation.model_copy(
                        update={
                            "deadline": window.prepared_at
                            + timedelta(seconds=window.effective_preparation_seconds),
                            "parent_operation_id": gen_op.operation_id,
                        }
                    )
                gen_control.checkpoint()
                preparation_active = False
                snapshot = execute_actor_generation(
                    ActorDispatch(
                        intent=GenerationPlanned(
                            operation=intent_operation, intent=intent
                        ),
                        expected_revision=snapshot.revision,
                        result_operation=cleanup(
                            prefix + "-response",
                            gen_op,
                            after_deadline=True,
                            seconds=(
                                None
                                if selected is None
                                else selected.result_ceiling_seconds(
                                    request.cleanup_seconds
                                )
                            ),
                        ),
                    ),
                    d.journal,
                    d.model,
                    d.controls,
                    clock=d.clock,
                )
                generation = snapshot.project().generation
                if generation is None:
                    continue  # An actual failed/uncertain response is already recorded.
                decision = ActorDecision.model_validate(
                    d.decisions.decide(
                        generation, request.task, cleanup(prefix + "-parse", gen_op)
                    )
                )
                if decision.generation_id != generation.generation_id:
                    raise OwnershipConflict(
                        "Actor decision changed original generation"
                    )
                if decision.outcome == "invalid":
                    op = cleanup(prefix + "-reject", gen_op)
                    event = DecisionRejected(operation=op, decision=decision)
                    after = TraceSnapshot.model_validate(
                        d.journal.append(event, snapshot.revision, op)
                    )
                    if (
                        after.plan != snapshot.plan
                        or after.creation_operation != snapshot.creation_operation
                        or after.events != (*snapshot.events, event)
                    ):
                        raise OwnershipConflict(
                            "Actor rejection did not confirm original decision"
                        )
                    snapshot = after
                    rejection_control = d.controls.bind(op)
                    rejected_inputs = (
                        d.decisions.rejected_inputs(
                            generation, decision, rejection_control
                        )
                        if isinstance(d.decisions, ActorRejectedInputReads)
                        else d.evidence
                    )
                    check_repeated_invalid_proposals(
                        snapshot, rejected_inputs, rejection_control
                    )
                    continue
                control.checkpoint()
                if decision.outcome == "read":
                    if d.readings is None:
                        raise OwnershipConflict(
                            "Original Actor input declared reads without a registered reader"
                        )
                    d.authority.verify(request, snapshot, control)
                    read_op = execute(
                        prefix + "-read", seconds=request.interaction_seconds
                    )
                    snapshot = execute_observation_read(
                        ObservationReadDispatch(
                            intent=ReadPlanned(
                                operation=execute(prefix + "-read-intent"),
                                decision=decision,
                                execution_operation=read_op,
                            ),
                            expected_revision=snapshot.revision,
                            result_operation=cleanup(
                                prefix + "-read-result", read_op, after_deadline=True
                            ),
                        ),
                        d.journal,
                        d.readings,
                        d.evidence,
                        d.controls,
                    )
                    continue
                step_op = execute(
                    prefix + "-step",
                    request.browser_allocation,
                    request.interaction_seconds,
                )
                snapshot = execute_browser_action(
                    BrowserDispatch(
                        intent=ActionPlanned(
                            operation=execute(prefix + "-action-intent"),
                            decision=decision,
                            execution_operation=step_op,
                        ),
                        expected_revision=snapshot.revision,
                        result_operation=cleanup(
                            prefix + "-interaction", step_op, after_deadline=True
                        ),
                    ),
                    d.journal,
                    d.browser,
                    d.controls,
                )
        except BaseException as primary:
            # Dispatcher preflight still belongs to preparation. Its validate
            # call precedes the durable trace intent and model.generate; later
            # phases may already have committed/sent and remain unconfirmed.
            preflight_unsent = (
                isinstance(primary, ActorDispatchFailure)
                and primary.phase == "preflight"
                and primary.request.intent.intent.execution_window is not None
                and primary.acknowledged is None
                and primary.returned is None
                and primary.observed is None
            )
            preparation_error = (
                primary.primary
                if preflight_unsent and isinstance(primary, ActorDispatchFailure)
                else primary
            )
            if (
                (preparation_active or preflight_unsent)
                and isinstance(preparation_error, OperationStopped)
                and preparation_error.reason_code == "DEADLINE_EXCEEDED"
            ):
                stopped = ActorRoundBudgetStopped(
                    request.operation.operation_id, preparation_index, "preparation"
                )
                stopped.__cause__ = primary
                primary = stopped
            errors: list[BaseException] = []
            # Only read/reconcile facts under independent cleanup. An unknown
            # first intent is not converted into a fabricated outcome or seal.
            if request_ref is not None:
                try:
                    read = cleanup("failure-read", request.operation)
                    actual = TraceSnapshot.model_validate(d.journal.read(read))
                    snapshot = actual
                    view = actual.project()
                    if (
                        not seal_attempted
                        and view.sealed is None
                        and view.action is None
                        and view.reading is None
                        and (view.intent is None or view.generation is not None)
                    ):
                        reason = (
                            "cancelled"
                            if isinstance(primary, OperationStopped)
                            and primary.reason_code == "CANCELLED"
                            else "error"
                        )
                        if view.halted and (
                            view.turns[-1].generation.status == "uncertain"
                            or (
                                view.turns[-1].reading is not None
                                and view.turns[-1].reading.outcome == "uncertain"
                            )
                        ):
                            reason = "uncertain"
                        last_interaction = (
                            view.turns[-1].interaction if view.turns else None
                        )
                        if last_interaction is not None:
                            result = last_interaction.result
                            if result is not None and result.terminal:
                                reason = "finished"
                        snapshot = seal(actual, reason, "failure-seal")
                except BaseException as cleanup_error:
                    errors.append(cleanup_error)
            raise ActorLoopFailure(
                primary, request_ref, snapshot, tuple(errors)
            ) from primary
        finally:
            if isinstance(d.context, ActorContextInputLifetime):
                d.context.clear_inputs()
