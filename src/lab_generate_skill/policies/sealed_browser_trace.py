"""Pure original sealed browser trace/source/limit and Actor request proof.

Extracted without changing the original Map read ordering or proof conditions.
Readers retain their site-specific page/return checks and actual evidence I/O.
"""

from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    IncompleteAnswerEvidence,
)


def require_original_sealed_browser_trace(
    run: RunPlan,
    journal: TraceSnapshot,
    trace: InteractionTrace,
    initial: InitialObservationInputs,
) -> None:
    plan = journal.plan
    run.check_binding(plan.binding.run)
    if plan.binding.task not in tuple(t.identity for t in run.tasks) or (
        plan.max_generations,
        plan.max_interactions,
    ) != (
        run.resources.max_actor_generations_per_attempt,
        run.resources.max_interactions_per_attempt,
    ):
        raise EvidenceIntegrityError(
            "Map sealed journal changed original frozen run task/limits"
        )
    if (
        journal.project().sealed != trace
        or plan.scope != initial.prepared.scope
        or trace.initial_observation_ref
        != initial.acquired.details.started.initial_observation_ref
        or plan.initial_observation_ref != trace.initial_observation_ref
        or (plan.max_generations, plan.max_interactions)
        != (trace.max_generations, trace.max_interactions)
    ):
        raise EvidenceIntegrityError(
            "Map judgment lost the original sealed Actor journal/initial state"
        )


def require_original_browser_actor_request(
    journal: TraceSnapshot,
    trace: InteractionTrace,
    initial: InitialObservationInputs,
    stop: ActorStop,
    request: ActorRunRequest,
) -> None:
    plan, browser = journal.plan, initial.browser
    if (
        stop.scope,
        stop.reason,
        stop.generations,
        stop.interactions,
        stop.final_observation_ref,
    ) != (
        trace.scope,
        trace.stop_reason,
        trace.generations,
        trace.interactions,
        trace.final_observation_ref,
    ) or (
        request.scope,
        request.task,
        request.browser_allocation,
        request.initial_observation_ref,
    ) != (
        trace.scope,
        initial.prepared.public_task,
        browser.token,
        trace.initial_observation_ref,
    ):
        raise EvidenceIntegrityError("Map judgment changed original Actor request/stop")
    if len(request.parameters_refs) != plan.max_generations or any(
        t.generation.parameters_ref != request.parameters_refs[i]
        for i, t in enumerate(trace.turns)
    ):
        raise EvidenceIntegrityError(
            "Map judgment changed original Actor generation parameters"
        )
    if trace.stop_reason in ("error", "uncertain", "cancelled"):
        raise IncompleteAnswerEvidence("Original Map Actor execution incomplete")
