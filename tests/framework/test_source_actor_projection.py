"""Exact frozen source policy, concrete selection and independent reread gates."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import json
import pytest
from lab_generate_skill.domain.actor_projection import (
    FullAxProjection,
    MapRailsDiagnosticProjection,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from source_actor_plan import plan_source_actor
from source_actor_projection import read_source_projection, original_source_projection
from source_actor_authority import SourceActorAuthority
from test_source_actor_assembly import setup
from map_actor_view_fixtures import original_request


@pytest.mark.parametrize("explicit", [False, True])
def test_original_full_AX_policy_and_explicit_v2_roundtrip_no_ignored_selection(
    tmp_path: Path, explicit: bool
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    plan = plan_source_actor(
        source,
        browser,
        actor,
        state.baseline_inputs.observation_ref,
        params,
        projection=FullAxProjection() if explicit else None,
    )
    assert isinstance(plan.run.workload, ExecutionWorkload)
    ref = plan.run.workload.execution_policy_ref
    assert ref.content_schema == "engineering-execution-policy/" + (
        "2" if explicit else "1"
    )
    raw = state.store.read(ref)
    fields = json.loads(raw)
    assert ("actor_projection" in fields) is explicit
    control = actor.controls.bind(plan.request.operation)
    assert (
        read_source_projection(ref, plan.request, plan.trace, state.store, control)
        == FullAxProjection()
    )
    assert (
        original_source_projection(plan.request, plan.trace, state.store, control)
        == plan.projection
    )
    assert state.store.read(ref) == raw
    snapshot = TraceSnapshot(
        plan=plan.trace, creation_operation=plan.request.operation, events=()
    )
    session: Any = SimpleNamespace(
        observation_ref=plan.request.initial_observation_ref,
        engine=SimpleNamespace(state="ready"),
    )
    SourceActorAuthority(source, browser, session, plan).verify(
        plan.request, snapshot, control
    )
    wrong = replace(plan, projection=MapRailsDiagnosticProjection())
    with pytest.raises(OwnershipConflict):
        SourceActorAuthority(source, browser, session, wrong).verify(
            plan.request, snapshot, control
        )


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "unknown",
        "bool-limit",
        "float-limit",
        "limit",
        "memory",
        "projection-null",
        "projection-extra",
        "projection-bool-version",
        "projection-wrong-scope",
        "duplicate",
        "nonfinite",
        "list",
        "empty",
        "wrong-schema",
        "wrong-visibility",
    ],
)
def test_policy_rejects_missing_unknown_wrong_types_and_task_mismatch(
    tmp_path: Path, change: str
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    plan = plan_source_actor(
        source,
        browser,
        actor,
        state.baseline_inputs.observation_ref,
        params,
        projection=FullAxProjection(),
    )
    assert isinstance(plan.run.workload, ExecutionWorkload)
    value = json.loads(state.store.read(plan.run.workload.execution_policy_ref))
    if change == "missing":
        del value["actor_projection"]
    elif change == "extra":
        value["silently_ignored"] = True
    elif change == "unknown":
        value["actor_projection"] = {"schema_version": "actor-unknown/1"}
    elif change == "bool-limit":
        value["max_generations"] = True
    elif change == "float-limit":
        value["max_generations"] = 20.0
    elif change == "limit":
        value["max_interactions"] += 1
    elif change == "memory":
        value["memory"] = {}
    elif change == "projection-null":
        value["actor_projection"] = None
    elif change == "projection-extra":
        value["actor_projection"]["ignored"] = True
    elif change == "projection-bool-version":
        value["actor_projection"] = {
            **MapRailsDiagnosticProjection().model_dump(),
            "contract_version": True,
        }
    elif change == "projection-wrong-scope":
        value["actor_projection"] = MapRailsDiagnosticProjection().model_dump()
    raw = json.dumps(value).encode()
    if change == "duplicate":
        raw = raw[:-1] + b', "max_generations": 20}'
    elif change == "nonfinite":
        raw = raw[:-1] + b', "bad": NaN}'
    elif change == "list":
        raw = b"[]"
    elif change == "empty":
        raw = b""
    schema = (
        "unsupported/1"
        if change == "wrong-schema"
        else "engineering-execution-policy/2"
    )
    ref = source.native.raw(raw, schema)
    if change == "wrong-visibility":
        ref = ref.model_copy(update={"visibility": "public"})
    with pytest.raises((EvidenceIntegrityError, OwnershipConflict)):
        read_source_projection(
            ref,
            plan.request,
            plan.trace,
            state.store,
            actor.controls.bind(plan.request.operation),
        )


def test_concrete_map_selection_decodes_original_public_task_and_refuses_wrong_binding(
    tmp_path: Path,
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    plan = plan_source_actor(
        source, browser, actor, state.baseline_inputs.observation_ref, params
    )
    request = original_request()
    value = dict(
        engineering_only=True,
        skill=request.skill.model_dump(mode="json"),
        memory=request.memory.model_dump(mode="json"),
        max_generations=plan.trace.max_generations,
        max_interactions=plan.trace.max_interactions,
        actor_projection=MapRailsDiagnosticProjection().model_dump(mode="json"),
    )
    ref = source.native.raw(
        json.dumps(value).encode(), "engineering-execution-policy/2"
    )
    control = actor.controls.bind(plan.request.operation)
    assert (
        read_source_projection(ref, request, plan.trace, state.store, control)
        == MapRailsDiagnosticProjection()
    )
    assert (
        read_source_projection(ref, request, plan.trace, state.store, control)
        == MapRailsDiagnosticProjection()
    )
    with pytest.raises(OwnershipConflict):
        read_source_projection(ref, plan.request, plan.trace, state.store, control)


def test_wrong_scope_plan_selection_rejected_before_any_publication(
    tmp_path: Path,
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    calls: list[object] = []
    source.native.raw = lambda *args: calls.append(args)
    source.native.put = lambda *args: calls.append(args)
    with pytest.raises(OwnershipConflict):
        plan_source_actor(
            source,
            browser,
            actor,
            state.baseline_inputs.observation_ref,
            params,
            projection=MapRailsDiagnosticProjection(),
        )
    assert calls == []


@pytest.mark.parametrize("workload", [None, "", {}, False])
def test_nonexecution_workload_rejected_before_original_policy_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload: Any
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    plan = plan_source_actor(
        source, browser, actor, state.baseline_inputs.observation_ref, params
    )
    snapshot = TraceSnapshot(
        plan=plan.trace, creation_operation=plan.request.operation, events=()
    )
    session: Any = SimpleNamespace(
        observation_ref=plan.request.initial_observation_ref,
        engine=SimpleNamespace(state="ready"),
    )
    plan = replace(plan, run=plan.run.model_copy(update={"workload": workload}))

    def read(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Invalid workload must fail before evidence read")

    monkeypatch.setattr(source.c.evidence, "read", read)
    with pytest.raises(OwnershipConflict):
        SourceActorAuthority(source, browser, session, plan).verify(
            plan.request, snapshot, actor.controls.bind(plan.request.operation)
        )
