"""Freeze explicit ordinary20 vs representative16 without any Actor execution."""

import json
from pathlib import Path
from actor_context_projection_fixtures import actor_projection_case
from typing import Any
import pytest
from test_source_actor_assembly import setup
from source_actor_plan import plan_source_actor
from source_actor_execution import execute_source_actor
from source_actor_callbacks import SourceActorCallbacks
from lab_generate_skill.domain.run_plan import ExecutionWorkload


@pytest.mark.parametrize("limit", [1, 16, 20])
def test_explicit_interaction_limit_matches_policy_run_and_trace(
    tmp_path: Path, limit: int
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    plan = plan_source_actor(
        source,
        browser,
        actor,
        state.baseline_inputs.observation_ref,
        params,
        max_interactions=limit,
    )
    assert (
        plan.run.resources.max_interactions_per_attempt
        == plan.trace.max_interactions
        == limit
    )
    assert isinstance(plan.run.workload, ExecutionWorkload)
    policy = json.loads(state.store.read(plan.run.workload.execution_policy_ref))
    assert policy["max_interactions"] == limit
    assert plan.trace.max_generations == len(plan.request.parameters_refs) == 20
    callback = SourceActorCallbacks(
        actor,
        actor,
        params,
        tmp_path,
        max_interactions=limit,
        context_policy=actor_projection_case().policy,
    )
    assert callback.max_interactions == limit


@pytest.mark.parametrize("bad", [None, True, False, "20", 0, -1, 21, [], {}, 1.5])
def test_invalid_limit_never_reads_source_or_creates_trace_directory(
    tmp_path: Path, bad: Any
) -> None:
    absent: Any = None
    with pytest.raises(ValueError, match="interaction limit"):
        plan_source_actor(absent, absent, absent, absent, absent, max_interactions=bad)
    with pytest.raises(ValueError, match="interaction limit"):
        execute_source_actor(
            absent,
            absent,
            absent,
            absent,
            absent,
            absent,
            tmp_path,
            max_interactions=bad,
            context_policy=actor_projection_case().policy,
        )
    with pytest.raises(ValueError, match="interaction limit"):
        SourceActorCallbacks(
            absent,
            absent,
            absent,
            tmp_path,
            max_interactions=bad,
            context_policy=actor_projection_case().policy,
        )
    assert list(tmp_path.iterdir()) == []
