"""Exact current initialization, sealed Actor and original browser binding."""

from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.actor_run import ActorStop, ActorRunRequest
from lab_generate_skill.domain.errors import OwnershipConflict, IncompleteAnswerEvidence


def require_original_task_capture(
    plan: TaskExecutionPlan,
    declaration: TaskCapturePlan,
    inputs: TaskCaptureInputs,
    snapshot: TraceSnapshot,
    browser: BrowserResourceSpec,
    stop: ActorStop,
    request: ActorRunRequest,
) -> None:
    actor = inputs.initialized.actor
    trace = snapshot.project().sealed
    if trace is None or trace.stop_reason in ("error", "uncertain", "cancelled"):
        raise IncompleteAnswerEvidence("Original complete sealed Actor trace required")
    if (
        snapshot.plan.binding != plan.intent.binding
        or snapshot.plan.scope != declaration.scope
        or actor.scope != declaration.scope
        or actor.operation != plan.operation
        or actor.skill.content_digest != plan.intent.skill_digest
        or request != actor
        or browser.token != actor.browser_allocation
        or browser.configuration.spec.scope != actor.scope
        or browser.configuration.spec.task != actor.task
        or trace.initial_observation_ref != actor.initial_observation_ref
        or snapshot.plan.initial_observation_ref != actor.initial_observation_ref
        or len(actor.parameters_refs) != snapshot.plan.max_generations
        or tuple(t.generation.parameters_ref for t in trace.turns)
        != actor.parameters_refs[: trace.generations]
        or (
            stop.scope,
            stop.reason,
            stop.generations,
            stop.interactions,
            stop.final_observation_ref,
        )
        != (
            trace.scope,
            trace.stop_reason,
            trace.generations,
            trace.interactions,
            trace.final_observation_ref,
        )
    ):
        raise OwnershipConflict(
            "Terminal capture changed original Actor/attempt/initial/stop"
        )
