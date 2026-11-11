"""Consume an already published initialization under its current live owner.

The caller retains original resource ownership until the executing append is
acknowledged. Pre-entry failure/unknown commit remains the caller's bounded
owner-scope cleanup responsibility. No upstream acquisition or initialization
is invoked; a closed or stopped run never becomes resumable through this API.
"""

from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot, AttemptEntry
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    RevisionConflict,
)
from lab_generate_skill.ports.task_execution_deps import TaskExecutionDeps
from .context_evidence import read_bytes
from .task_cleanup_budget import require_frozen_task_cleanup_budget
from .task_execution_events import TaskExecutionEvents
from .task_execution_tail import TaskTailState, execute_task_tail, verify_task_current
from .task_completion import CompletedTaskExecution
from .execute_task import _completed_task, _finish


def execute_initialized_task(
    plan: TaskExecutionPlan,
    deps: TaskExecutionDeps,
    initialized_ref: EvidenceRef,
    *,
    expected_revision: int,
) -> CompletedTaskExecution:
    """Run only Actor→capture/judgment→close/reset on a current frozen prefix.

    Exact original plan/body/revision and all original dynamic rights are
    mandatory. This is not a cross-job ownership transfer or retry grant.
    """
    plan = TaskExecutionPlan.model_validate(plan)
    initialized_ref = EvidenceRef.model_validate(initialized_ref)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Exact nonnegative frozen run revision required")
    if any(value is None for value in vars(deps).values()):
        raise ValueError("All original task dependencies are mandatory")
    private_state_ref(initialized_ref, "initialized-task/1")
    control = deps.controls.bind(plan.operation)
    control.checkpoint()
    snapshot = RunSnapshot.model_validate(deps.runs.read(plan.read_operation))
    if snapshot.revision != expected_revision:
        raise RevisionConflict("Frozen initialized prefix changed before entry")
    run, attempts = snapshot.project()
    attempt = next((a for a in attempts if a.binding == plan.intent.binding), None)
    if (
        snapshot.binding != plan.intent.binding.run
        or run.stage != "running"
        or run.stop_reason is not None
        or attempt is None
        or attempt.stage != "baseline_verified"
        or attempt.stop_reason is not None
    ):
        raise InvalidTransition("Current unstopped baseline_verified attempt required")
    plans = [
        r for r in attempt.events[0].outputs if r.content_schema == plan.schema_version
    ]
    if (
        len(plans) != 1
        or read_bytes(deps.evidence, plans[0], 16 * 1024**2, control)
        != plan.model_dump_json().encode()
    ):
        raise OwnershipConflict(
            "Initialized entry changed original published task plan"
        )
    raw = read_bytes(deps.evidence, initialized_ref, 16 * 1024**2, control)
    initialized = InitializedTask.model_validate_json(raw)
    if (
        initialized.model_dump_json().encode() != raw
        or initialized.actor.operation != plan.operation
        or initialized.actor.scope.owner != plan.intent.binding.run.owner
        or initialized.actor.scope.task != plan.intent.binding.task
        or initialized.actor.scope.attempt_id != plan.intent.binding.attempt_id
        or not {initialized.baseline_ref, initialized.equivalence_ref}.issubset(
            attempt.events[-1].outputs
        )
    ):
        raise OwnershipConflict(
            "Frozen initialization changed original actor/baseline scope"
        )
    require_frozen_task_cleanup_budget(plan, deps.evidence, control)
    state = deps.source.open(plan, snapshot, control)
    if state.binding != plan.intent.binding:
        raise OwnershipConflict("Initialized entry changed original source binding")
    verify_task_current(plan, deps, snapshot, state, plan.operation)
    reset = ResetPlan.model_validate_json(
        read_bytes(deps.evidence, plan.reset_plan_ref, 2 * 1024**2, control)
    )
    if (reset.scope.owner, reset.scope.task, reset.scope.attempt_id) != (
        plan.intent.binding.run.owner,
        plan.intent.binding.task,
        plan.intent.binding.attempt_id,
    ):
        raise OwnershipConflict("Initialized entry changed original reset scope")
    deps.source.verify_resources(plan, state, snapshot, reset, control)
    requirements = EvidenceRequirements.model_validate(
        deps.evaluator.requirements(plan.evaluation)
    )
    if requirements != plan.evaluation.requirements:
        raise OwnershipConflict(
            "Initialized entry changed original capture requirements"
        )
    deps.capture.preflight(plan, requirements, control)
    verify_task_current(plan, deps, snapshot, state, plan.operation)
    events = TaskExecutionEvents(
        plan, deps.runs, deps.evidence, deps.controls, deps.clock, snapshot, deps.source
    )
    events.known.update(plan=plans[0], initialized=initialized_ref)
    events.last_entry = next(
        (
            e
            for e in reversed(snapshot.entries)
            if isinstance(e, AttemptEntry) and e.binding == plan.intent.binding
        ),
        None,
    )
    tail = TaskTailState()
    primary: BaseException | None = None
    cleanup_errors: list[BaseException] = []
    try:
        execute_task_tail(plan, deps, state, initialized, events, tail)
    except BaseException as error:
        primary = error
    finally:
        # A duplicate/stale caller must not close the winning caller's resources.
        # Before an acknowledged executing append, the original owner scope
        # retains physical cleanup and any unknown-commit reconciliation.
        if tail.entered:
            _finish(plan, deps, reset, events, primary, cleanup_errors, tail.trace)
    return _completed_task(
        plan, initialized, tail.trace, tail.evaluation, events, primary, cleanup_errors
    )
