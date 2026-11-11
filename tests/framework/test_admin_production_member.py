"""Outer composition with explicit unit model/site/task premises.

Original admission/owner and typed declarations are reused. Inject only resource
and task effects to check ordering/partial cleanup here; actual native execution
and full independent review are not inferred from this routing check.
"""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import sys
import pytest
import admin_production_member as module
from admin_production_member import execute_claimed_admin_member
from admin_production_admission import ClaimedAdminMember
from admin_production_site import DeclaredAdminSite
from admin_production_execution import site_acquisition_context
from lab_generate_skill.bootstrap.task_actor import TaskActorResources
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from construction_storage_fixtures import put
from actor_resource_fixtures import resource_case
from test_admin_production_admission import case as case
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_input import contracts as contracts


@pytest.fixture
def routing(case: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    c, kw, _ = case
    base, resources = c.source.site, c.owned.resources
    member = ClaimedAdminMember(c.admitted, c.declarations, resources.owner)
    unit_model = resource_case(tmp_path / "unit-actor", Path(sys.executable))
    spec = unit_model.spec.model_copy(
        update={
            "token": resources.model.binding.resource,
            "release_ref": member.owner.run.release_ref,
            "model_binding_ref": resources.model.binding.model_binding_ref,
        }
    )
    model_op = kw["operation"].model_copy(
        update={
            "operation_id": "unit-admin-model",
            "allocation_id": spec.token.allocation_id,
            "recovery_ref": spec.token.recovery_ref,
        }
    )
    frozen = c.admitted.reader.verify_source(
        c.admitted.published.source,
        kw["operation"],
        base.controls.bind(kw["operation"]),
    )
    actor = TaskActorInitialization(
        candidate_id=frozen.policy.candidate_id,
        revision_round=0,
        context_configuration_ref=frozen.policy.actor_context_ref,
        memory=frozen.policy.memory,
        model_allocation=spec.token,
        parameters_refs=(frozen.run.models[0].parameters_ref,),
        generation_seconds=60,
        interaction_seconds=60,
        cleanup_seconds=60,
    )
    public = PublicTask.model_validate_json(
        base.evidence.read(frozen.source.task.public_task_ref)
    )
    candidate = DeclaredAdminSite(
        resources.site.spec,
        resources.site.operation,
        public,
        frozen.source.task.baseline_ref,
        True,
    )
    output = tmp_path / "member"
    output.mkdir()
    args = dict(
        member=member,
        source=c.source.qualified,
        candidate=candidate,
        model=spec,
        model_operation=model_op,
        template=c.source.qualified.material.browser.configuration,
        actor=actor,
        journal=base.journal,
        controls=base.controls,
        clock=base.clock,
        allocation_verifier=unit_model.allocation_verifier,
        output=output,
        site_seconds=120,
    )
    events = []
    state = SimpleNamespace(fault=None)

    @contextmanager
    def acquire(*a: Any, **k: Any) -> Any:
        try:
            events.append("model-acquire")
            if state.fault == "model-acquire":
                raise OSError(state.fault)
            yield SimpleNamespace()
        finally:
            events.append("model-close")

    def scope(*a: Any, **k: Any) -> Any:
        events.append("model-bind")
        if state.fault == "model-bind":
            raise OSError(state.fault)
        return resources.model

    monkeypatch.setattr(module, "claimed_actor_resource", acquire)
    monkeypatch.setattr(module, "ActorExecutionScope", scope)
    original_acquisition = site_acquisition_context

    def late(*a: Any, **k: Any) -> Any:
        events.append("site-deadline")
        assert "model-bind" in events
        return original_acquisition(*a, **k)

    monkeypatch.setattr(module, "site_acquisition_context", late)
    result = ExecutionTaskResult(
        intent=c.declarations.plan.intent,
        attempt_ref=put(base.evidence, {"unit": True}, "execution-attempt-result/1"),
        evaluation=Evaluation(
            identity=public.identity,
            attempt_id=frozen.inputs.attempt_id,
            contract_ref=frozen.inputs.task_binding_ref,
            evaluator_id="unit-routing",
            evaluator_version="1",
            status="unknown",
            reward=None,
            checks=(),
            reason_code="UNIT_ROUTING_ONLY",
        ),
        evaluation_ref=put(base.evidence, {"unit": True}, "evaluation/1"),
        generations=0,
        interactions=0,
    )
    actors = c.owned.bundle.task.deps.actors
    fake_resources = TaskActorResources(resources.model, None, SimpleNamespace(read=lambda *a: "unit-snapshot"), output / "calls", [])  # type: ignore[arg-type]
    actors.resources = lambda *a: fake_resources

    def execute(*a: Any, **k: Any) -> Any:
        events.append("execute")
        if state.fault == "execute":
            raise OSError(state.fault)
        actors.resources(None, None)
        return result

    owned = SimpleNamespace(
        bundle=SimpleNamespace(
            preparation=c.owned.bundle.preparation,
            task=SimpleNamespace(deps=SimpleNamespace(actors=actors), execute=execute),
        )
    )

    def bind(*a: Any, **k: Any) -> Any:
        events.append("site-bind")
        if state.fault == "site-bind":
            raise OSError(state.fault)
        return owned

    def review(*a: Any, **k: Any) -> Any:
        events.append("review-inputs")
        assert events[-2] == "model-close"
        if state.fault == "review-inputs":
            raise OSError(state.fault)
        return {"unit_routing_only": True}

    monkeypatch.setattr(module, "bind_admin_production_execution", bind)
    monkeypatch.setattr(module, "completed_admin_review_inputs", review)
    monkeypatch.setattr(
        base.journal, "read", lambda *a, **k: SimpleNamespace(state="closed")
    )
    return args, events, state, result, c


def test_original_scopes_late_site_and_closed_review_order(routing: Any) -> None:
    args, events, _, expected, c = routing
    result = execute_claimed_admin_member(**args)
    assert result.result is expected
    assert events == [
        "model-acquire",
        "model-bind",
        "site-deadline",
        "site-bind",
        "execute",
        "model-close",
        "review-inputs",
    ]
    assert set(result.phase_seconds) == {
        "model_acquisition",
        "task_lifecycle",
        "model_close",
    }
    assert c.owned.resources.site.phase == "new"


@pytest.mark.parametrize(
    "fault", ["model-acquire", "model-bind", "site-bind", "execute", "review-inputs"]
)
def test_partial_or_task_failure_closes_original_scope_and_retains_claim(
    routing: Any, fault: str
) -> None:
    args, events, state, _, c = routing
    state.fault = fault
    before = {p.name: p.read_bytes() for p in c.admitted.claims._root.glob("*.json")}
    with pytest.raises(OSError, match=fault) as caught:
        execute_claimed_admin_member(**args)
    assert "model-close" in events
    assert getattr(caught.value, "admin_original_member") is args["member"]
    assert getattr(caught.value, "admin_task_result") is (
        routing[3] if fault == "review-inputs" else None
    )
    if fault != "review-inputs":
        assert "review-inputs" not in events
    assert before == {
        p.name: p.read_bytes() for p in c.admitted.claims._root.glob("*.json")
    }


def test_final_identity_rejects_before_original_model_scope(routing: Any) -> None:
    args, events, _, _, _ = routing
    args["model"] = args["model"].model_copy(
        update={"release_ref": args["source"].material.context_ref}
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        execute_claimed_admin_member(**args)
    assert events == []


def test_cancellation_after_model_bind_closes_scope_without_task_dispatch(
    routing: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, events, _, _, _ = routing

    def cancel(*a: Any, **k: Any) -> Any:
        raise OperationStopped("CANCELLED", "unit-cancel")

    monkeypatch.setattr(module, "site_acquisition_context", cancel)
    with pytest.raises(OperationStopped, match="CANCELLED"):
        execute_claimed_admin_member(**args)
    assert events == ["model-acquire", "model-bind", "model-close"]
