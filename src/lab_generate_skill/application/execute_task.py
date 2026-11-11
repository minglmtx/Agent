"""One shared original task lifecycle, using existing admission/Actor/evaluator ports.

Resources/initialization/capture/restore are trusted composition seams over the
original adapters, never application imports of concrete sites or test wrappers.
An existing attempt is never acquired or executed again. Failure retains original
facts and exceptions while independently attempting bounded original cleanup.
"""

from contextlib import ExitStack
from .execution_stage import execution_stage
from .task_execution_tail import (
    TaskTailState,
    execute_task_tail,
    verify_task_current as _live,
)
from lab_generate_skill.domain.task_admission import TaskAdmissionState
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    TaskCaptureResult,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_completion import TaskCompletionFacts
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.execution import StopReason, ExecutionFailure
from lab_generate_skill.ports.task_execution_deps import (
    TaskExecutionDeps as TaskExecutionDeps,
)
from lab_generate_skill.ports.task_finalization import RestoredTaskResetReader
from .task_completion import CompletedTaskExecution
from .actor_loop import ActorLoopFailure
from .context_evidence import read_bytes
from .task_cleanup_budget import require_frozen_task_cleanup_budget
from .task_execution_events import TaskExecutionEvents, task_stop_reason


class TaskExecutionUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: TaskExecutionPlan,
        primary: BaseException | None,
        cleanup_errors: tuple[BaseException, ...],
        events: TaskExecutionEvents,
        initialized: InitializedTask | None,
        trace: TraceSnapshot | None,
        evaluation: Evaluation | None,
    ) -> None:
        self.plan, self.primary, self.cleanup_errors = plan, primary, cleanup_errors
        self.snapshot, self.last_entry = events.snapshot, events.last_entry
        self.known, self.retained = dict(events.known), tuple(events.retained)
        self.initialized, self.trace, self.evaluation = initialized, trace, evaluation
        super().__init__(
            "Original task lifecycle unconfirmed; retain facts/recover original resources, never execute this attempt again"
        )


def execute_task(
    plan: TaskExecutionPlan, deps: TaskExecutionDeps
) -> CompletedTaskExecution:
    plan = TaskExecutionPlan.model_validate(plan)
    if any(value is None for value in vars(deps).values()):
        raise ValueError(
            "Every original task lifecycle/authority dependency is mandatory"
        )
    with ExitStack() as preparation_stage:
        preparation_stage.enter_context(
            execution_stage(deps.controls, "preparation", plan.operation)
        )
        return _execute_task(plan, deps, preparation_stage)


def _execute_task(
    plan: TaskExecutionPlan, deps: TaskExecutionDeps, preparation_stage: ExitStack
) -> CompletedTaskExecution:
    control = deps.controls.bind(plan.operation)
    control.checkpoint()
    require_frozen_task_cleanup_budget(plan, deps.evidence, control)
    snapshot = RunSnapshot.model_validate(deps.runs.read(plan.read_operation))
    state = TaskAdmissionState.model_validate(deps.source.open(plan, snapshot, control))
    if state.binding != plan.intent.binding:
        raise OwnershipConflict("Task source changed original attempt binding")
    _live(plan, deps, snapshot, state, plan.operation)
    if any(
        a.binding.attempt_id == plan.intent.binding.attempt_id
        for a in snapshot.project()[1]
    ):
        raise DispatchAlreadyCommitted(
            "Original task attempt already registered; no lifecycle replay"
        )
    reset = ResetPlan.model_validate_json(
        read_bytes(deps.evidence, plan.reset_plan_ref, 2 * 1024**2, control)
    )
    if (reset.scope.owner, reset.scope.task, reset.scope.attempt_id) != (
        plan.intent.binding.run.owner,
        plan.intent.binding.task,
        plan.intent.binding.attempt_id,
    ):
        raise OwnershipConflict("Task reset plan changed original scope")
    deps.source.verify_resources(plan, state, snapshot, reset, control)
    requirements = EvidenceRequirements.model_validate(
        deps.evaluator.requirements(plan.evaluation)
    )
    if requirements != plan.evaluation.requirements:
        raise OwnershipConflict(
            "Evaluator narrowed or changed original capture requirements"
        )
    deps.capture.preflight(plan, requirements, control)
    _live(plan, deps, snapshot, state, plan.operation)
    events = TaskExecutionEvents(
        plan, deps.runs, deps.evidence, deps.controls, deps.clock, snapshot, deps.source
    )
    initialized: InitializedTask | None = None
    tail = TaskTailState()
    primary: BaseException | None = None
    cleanup_errors: list[BaseException] = []
    effects_started = False
    try:
        plan_ref = events.put("plan", plan, plan.operation)
        events.append("planned", events.operation("planned"), (plan_ref,))
        op = events.operation("acquiring")
        events.append("acquiring", op, (plan_ref, plan.reset_plan_ref))
        _live(plan, deps, events.snapshot, state, op)
        deps.source.verify_resources(
            plan, state, events.snapshot, reset, deps.controls.bind(op)
        )
        effects_started = True
        acquired = deps.preparation.acquire(plan, op, deps.controls.bind(op))
        if (
            not isinstance(acquired, tuple)
            or not acquired
            or any(not isinstance(r, EvidenceRef) for r in acquired)
        ):
            raise ValueError(
                "Original acquisition must return nonempty attributable evidence"
            )
        op = events.operation("preparing")
        events.append("preparing", op, acquired)
        _live(plan, deps, events.snapshot, state, op)
        prepared = deps.preparation.prepare(plan, op, deps.controls.bind(op))
        if (
            not isinstance(prepared, tuple)
            or not prepared
            or any(not isinstance(r, EvidenceRef) for r in prepared)
        ):
            raise ValueError(
                "Original preparation must return nonempty attributable evidence"
            )
        preparation_stage.close()
        with execution_stage(deps.controls, "initialization", plan.operation):
            op = events.operation("starting")
            events.append("starting", op, prepared)
            _live(plan, deps, events.snapshot, state, op)
            initialized = InitializedTask.model_validate(
                deps.initialization.start(plan, op, deps.controls.bind(op))
            )
            events.put("initialized", initialized, op)
            events.append(
                "baseline_verified",
                events.operation("baseline"),
                (initialized.baseline_ref, initialized.equivalence_ref),
            )
        execute_task_tail(plan, deps, state, initialized, events, tail)
    except BaseException as error:
        primary = error
        if isinstance(error, ActorLoopFailure):
            tail.trace = error.snapshot
    finally:
        if effects_started:
            _finish(plan, deps, reset, events, primary, cleanup_errors, tail.trace)
    return _completed_task(
        plan, initialized, tail.trace, tail.evaluation, events, primary, cleanup_errors
    )


def _completed_task(
    plan: TaskExecutionPlan,
    initialized: InitializedTask | None,
    trace: TraceSnapshot | None,
    evaluation: Evaluation | None,
    events: TaskExecutionEvents,
    primary: BaseException | None,
    cleanup_errors: list[BaseException],
) -> CompletedTaskExecution:
    if primary is not None or cleanup_errors:
        unconfirmed = TaskExecutionUnconfirmed(
            plan, primary, tuple(cleanup_errors), events, initialized, trace, evaluation
        )
        raise unconfirmed from (primary if primary is not None else cleanup_errors[0])
    if (
        initialized is None
        or trace is None
        or evaluation is None
        or "reset" not in events.known
    ):
        raise InvalidTransition("Original complete task facts not available")
    sealed = trace.project().sealed
    assert sealed is not None
    try:
        facts = TaskCompletionFacts(
            intent=plan.intent,
            plan_ref=events.known["plan"],
            actor_request_ref=events.known["actor_request"],
            baseline_ref=initialized.baseline_ref,
            equivalence_ref=initialized.equivalence_ref,
            trace_ref=events.known["trace"],
            capture_ref=events.known["capture"],
            evaluation_ref=events.known["evaluation"],
            closed_ref=events.known["closed"],
            reset_ref=events.known["reset"],
            generations=sealed.generations,
            interactions=sealed.interactions,
        )
        return CompletedTaskExecution(
            plan, facts, evaluation, initialized, trace, events
        )
    except BaseException as error:
        raise TaskExecutionUnconfirmed(
            plan, error, (), events, initialized, trace, evaluation
        ) from error


def _finish(
    plan: TaskExecutionPlan,
    deps: TaskExecutionDeps,
    reset: ResetPlan,
    events: TaskExecutionEvents,
    primary: BaseException | None,
    errors: list[BaseException],
    trace: TraceSnapshot | None,
) -> None:
    """Physical close is attempted even if diagnostics/journal fail; no reset
    until original closure authority and an acknowledged restoring stage.
    """
    main_failure: ExecutionFailure | None = None
    stop = task_stop_reason(primary)
    closing = events.operation("closing", cleanup=True)
    outputs: tuple[EvidenceRef, ...] = (events.known["plan"],)
    try:
        if trace is not None and "trace_snapshot" not in events.known:
            events.put("trace_snapshot", trace, closing)
        if primary is not None:
            main_failure = events.diagnostic("primary_failure", primary, closing)
            outputs = (events.put("primary_failure", main_failure, closing),)
        events.append(
            "closing", closing, outputs, cleanup=True, primary=main_failure, stop=stop
        )
    except BaseException as error:
        errors.append(error)
    closed: ClosedTaskResources | None = None
    closed_requires_validation = False
    try:
        closed = ClosedTaskResources.model_validate(
            deps.finalization.close(plan, reset, closing, deps.controls.bind(closing))
        )
        if closed.reset_plan != reset or closed.reset_plan_ref != plan.reset_plan_ref:
            raise OwnershipConflict("Original close returned another reset plan")
        for value, ref in zip(closed.closures, closed.closure_refs, strict=True):
            if (
                read_bytes(deps.evidence, ref, 2 * 1024**2, deps.controls.bind(closing))
                != value.model_dump_json().encode()
            ):
                raise OwnershipConflict(
                    "Closure reference differs from complete original bytes"
                )
        deps.authority.verify_closed(plan, closed, closing, deps.controls.bind(closing))
        outputs = (events.put("closed", closed, closing),)
    except BaseException as error:
        known_closed = (
            closed if closed is not None else getattr(error, "known_closed", None)
        )
        closed = None
        errors.append(error)
        if (
            isinstance(known_closed, ClosedTaskResources)
            and known_closed.reset_plan == reset
            and known_closed.reset_plan_ref == plan.reset_plan_ref
        ):
            # This is a producer's retained fact, never a restoration grant.
            # Read and authorize it under the fresh original cleanup operation.
            closed = known_closed
            closed_requires_validation = True
    restoring = events.operation("restoring", cleanup=True)
    restoring_confirmed = False
    try:
        diagnostics = tuple(
            events.diagnostic("restore_failure_" + str(i), e, restoring)
            for i, e in enumerate(errors)
        )
        if diagnostics:
            outputs = tuple(
                events.put("cleanup_failure_" + str(i), e, restoring)
                for i, e in enumerate(diagnostics)
            )
        if diagnostics:
            main_failure = main_failure or diagnostics[0]
            stop = stop or "error"
        events.append(
            "restoring",
            restoring,
            outputs,
            cleanup=True,
            primary=main_failure,
            stop=stop,
            failures=diagnostics,
        )
        restoring_confirmed = True
    except BaseException as error:
        errors.append(error)
    if closed is not None and restoring_confirmed:
        try:
            if closed_requires_validation:
                for value, closure_ref in zip(
                    closed.closures, closed.closure_refs, strict=True
                ):
                    if (
                        read_bytes(
                            deps.evidence,
                            closure_ref,
                            2 * 1024**2,
                            deps.controls.bind(restoring),
                        )
                        != value.model_dump_json().encode()
                    ):
                        raise OwnershipConflict(
                            "Retained original closure changed complete receipt bytes"
                        )
                deps.authority.verify_closed(
                    plan, closed, restoring, deps.controls.bind(restoring)
                )
            ref = EvidenceRef.model_validate(
                deps.finalization.restore(
                    plan, closed, restoring, deps.controls.bind(restoring)
                )
            )
            receipt = (
                deps.finalization.load_restored_reset(
                    ref, restoring, deps.controls.bind(restoring)
                )
                if isinstance(deps.finalization, RestoredTaskResetReader)
                else deps.states.load_reset(ref, restoring)
            )
            if (
                receipt.plan_ref != plan.reset_plan_ref
                or receipt.scope != reset.scope
                or receipt.closure_refs != closed.closure_refs
                or receipt.status != "safe"
            ):
                raise OwnershipConflict(
                    "Original restoration/reset is incomplete or unsafe"
                )
            events.known["reset"] = ref
            outputs = (ref,)
        except BaseException as error:
            errors.append(error)
    seal = events.operation("sealed", cleanup=True)
    try:
        diagnostics = tuple(
            events.diagnostic("seal_failure_" + str(i), e, seal)
            for i, e in enumerate(errors)
        )
        if diagnostics:
            outputs = tuple(
                events.put("final_cleanup_failure_" + str(i), e, seal)
                for i, e in enumerate(diagnostics)
            )
        if diagnostics:
            main_failure = main_failure or diagnostics[0]
            stop = stop or "error"
        events.append(
            "sealed",
            seal,
            outputs,
            cleanup=True,
            primary=main_failure,
            stop=stop,
            failures=diagnostics,
        )
    except BaseException as error:
        errors.append(error)
