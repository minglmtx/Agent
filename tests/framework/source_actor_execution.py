"""Original registered model plus actual source/browser/trace engineering assembly."""

from pathlib import Path
from typing import Any
from lab_generate_skill.application.actor_loop import (
    ActorLoopFailure,
)
from lab_generate_skill.bootstrap.actor_runtime import original_actor_runtime
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.application.actor_context_preparation import (
    ActorContextRejected,
)
from lab_generate_skill.domain.actor_projection import (
    ActorProjectionConfiguration,
    actor_projection_configuration,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.local_actor import LocalActorExecution
from actor_resource_fixtures import ResourceCase as ActorCase
from browser_resource_fixtures import ResourceCase as BrowserCase
from actor_source_protocol import ActorSource
from source_actor_plan import plan_source_actor
from source_actor_authority import SourceActorAuthority
from source_actor_trace import SourceTraceAuthority


def execute_source_actor(
    source: ActorSource,
    browser: BrowserCase,
    session: EvidenceBrowserSession,
    actor: ActorCase,
    model_scope: ActorExecutionScope,
    params: LocalActorParameters,
    root: Path,
    *,
    context_policy: ContextProjectionPolicy,
    max_interactions: int = 16,
    projection: ActorProjectionConfiguration | None = None,
) -> tuple[dict[str, Any], BaseException | None]:
    if type(max_interactions) is not int or not 1 <= max_interactions <= 20:
        raise ValueError("Explicit engineering interaction limit must be integer1..20")
    if projection is not None:
        projection = actor_projection_configuration(projection)
    assert session.observation_ref is not None
    root.mkdir()
    (root / "trace").mkdir()
    (root / "calls").mkdir()
    plan = plan_source_actor(
        source,
        browser,
        actor,
        session.observation_ref,
        params,
        max_interactions=max_interactions,
        projection=projection,
        context_policy=context_policy,
    )
    completed: list[LocalActorExecution] = []
    trace_authority = SourceTraceAuthority(
        plan.trace, actor.evidence, actor.controls, completed
    )
    journal = FileTraceJournal(
        root / "trace", plan.trace, actor.controls, actor.evidence, trace_authority
    )
    journal.create(
        plan.trace,
        plan.request.operation.model_copy(
            update={"operation_id": "source-trace-create"}
        ),
    )
    live = SourceActorAuthority(source, browser, session, plan)
    runtime = original_actor_runtime(
        plan.request,
        journal,
        model_scope,
        session,
        actor.evidence,
        actor.controls,
        actor.clock,
        live,
        root / "calls",
        completed,
    )
    runner = runtime.runner
    n = source.native
    result: dict[str, Any] = dict(
        engineering_only=True,
        formal_source_admission=False,
        run_plan_ref=plan.trace.binding.run.plan_ref.model_dump(mode="json"),
        planned_actor_request_ref=n.put(plan.request).model_dump(mode="json"),
        trace_ref=None,
        runtime_error=None,
    )
    failure: BaseException | None = None
    snapshot = None
    try:
        snapshot = runner.run(plan.request)
    except ActorLoopFailure as error:
        failure, snapshot = error, error.snapshot
        result["runtime_error"] = describe_error(error.primary).model_dump(mode="json")
        if isinstance(error.primary, ActorContextRejected):
            result["context_rejection"] = error.primary.prepared.model_dump(mode="json")
    finally:
        result["executions"] = [
            n.put(value).model_dump(mode="json") for value in completed
        ]
        result["verified_model_returns"] = len(completed)
        result["model_call_total_known"] = (
            snapshot is not None and snapshot.project().sealed is not None
        )
        if snapshot is not None:
            result["trace_snapshot_ref"] = n.put(snapshot).model_dump(mode="json")
            trace = snapshot.project().sealed
            if trace is not None:
                result.update(
                    trace_ref=n.put(trace).model_dump(mode="json"),
                    stop_reason=trace.stop_reason,
                    generations=trace.generations,
                    interactions=trace.interactions,
                )
    return result, failure
