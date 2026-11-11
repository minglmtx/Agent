"""Entry routing with explicit supplied-runtime/native/task unit premises.

Low-level configuration, qualification, admission and model closure have their
own checks. Here only original producer/consumer ordering and refusal to enter
Actor after a failed source/claim are checked. Actual runtime supply, real source
qualification and full independent review remain unverified by these mocks.
"""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import pytest
import admin_production_entry as module
from admin_production_entry import AdminProductionRuntime, execute_admin_navigation
from admin_production_inputs import SelectedAdminNavigation
from production_inputs import OriginalDocuments
from admin_production_task_plan import AdminProductionBudgets
from admin_production_member import execute_claimed_admin_member
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.admin_navigation_origin import AdminNavigationOrigin
from test_admin_production_member import routing as routing
from test_admin_production_admission import case as case
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_input import contracts as contracts
from test_admin_production_task_plan import frozen_case
from datetime import timedelta
from lab_generate_skill.domain.operation_window import OperationTimeWindow
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls


@pytest.fixture
def entry(routing: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    a, model_events, _, result, c = routing
    base = c.source.site
    now = base.clock.utcnow()
    controls = BoundedOperationControls(
        base.controls,
        base.clock,
        OperationTimeWindow(
            owner=a["model"].token.owner,
            execution_deadline=now + timedelta(seconds=300),
            cleanup_deadline=now + timedelta(seconds=600),
            hard_end=now + timedelta(seconds=660),
        ),
    )
    private = AdminNavigationSpec.model_validate_json(
        base.evidence.read(c.owned.resources.owner.task.private_spec_ref)
    )
    public = PublicTask.model_validate_json(
        base.evidence.read(c.owned.resources.owner.task.public_task_ref)
    )
    selected = SelectedAdminNavigation(
        base.evidence.read(private.native_contract_ref),
        private.native_contract_ref,
        private,
        public.goal,
    )
    frozen = frozen_case(c)
    events = []
    state = SimpleNamespace(fault=None, qualified_source=c.source.qualified)
    # This unit check never claims to supply actual managed metadata permission.
    monkeypatch.setattr(
        AdminProductionRuntime,
        "check",
        lambda self, sel: events.append("runtime-check"),
    )
    r = AdminProductionRuntime(
        c.source.owner,
        c.declarations.preparation.scope,
        OriginalDocuments(base.evidence, base.controls),
        c.declarations.plan.read_operation,
        a["model"],
        a["model_operation"],
        cast(Any, None),
        cast(Any, None),
        b"unit-routing-only",
        frozen.run.release_ref,
        a["template"],
        cast(Any, None),
        c.source.read_factory(base.evidence, c.declarations.plan.read_operation),
        base.journal,
        controls,
        base.clock,
        a["allocation_verifier"],
        a["output"],
        a["output"] / "source",
        a["output"] / "candidate",
        c.admitted.claims._root,
        "unit-admin-navigation",
        cast(Any, None),
        cast(Any, None),
        public.allowed_actions,
        AdminProductionBudgets(
            schema_version="admin-navigation-production-budgets/2",
            task_seconds=20,
            post_claim_setup_seconds=1,
            metadata_cleanup_seconds=60,
        ),
        SourceRecoveryBudgets(
            preparation_metadata_seconds=30,
            browser_close_seconds=30,
            restore_seconds=30,
            resume_seconds=30,
            reset_facts_seconds=30,
            site_close_seconds=30,
        ),
    )
    # This routing fixture already substitutes source qualification. Supply
    # its explicit state-reader declaration/proof ABI too; these inert objects
    # cannot authorize actual managed storage or launch a state worker.
    r.source_reads.scope = cast(Any, object())
    r.source_reads.admission = cast(Any, object())
    state_proof = SimpleNamespace(last_reply=None)

    def state_reader(scope: Any, store: Any, admission: Any, task: Any) -> Any:
        assert scope is r.source_reads.scope and admission is r.source_reads.admission
        assert store is base.evidence and task == r.scope.task
        return state_proof

    monkeypatch.setattr(module, "SupervisedStateChecks", state_reader)
    inputs = SimpleNamespace(
        policy=frozen.policy,
        context_ref=frozen.context_ref,
        parameters_ref=frozen.parameters_ref,
    )

    def actor(*args: Any, **kw: Any) -> Any:
        events.append("actor-inputs")
        return inputs

    monkeypatch.setattr(module, "publish_known_actor_inputs", actor)

    def site(*args: Any, **kw: Any) -> Any:
        events.append(kw["prefix"] + "-declaration")
        assert kw["defer_acquisition"] == (kw["prefix"] == "execution")
        if kw["prefix"] == "execution":
            return a["candidate"]
        return SimpleNamespace(
            spec=c.source.qualified.material.site,
            acquisition=c.source.site.op,
            public=public,
        )

    monkeypatch.setattr(module, "declare_original_admin_site", site)

    def source(*args: Any, **kw: Any) -> Any:
        events.append("qualify-source")
        if state.fault == "source":
            raise OSError("source unconfirmed")
        if kw.get("retained_source") is not None:
            assert kw["retained_source"] == c.source.qualified.material
            assert kw["state_checks"] is None
            return c.source.qualified
        assert kw["state_checks"] is state_proof
        state_proof.last_reply = SimpleNamespace(
            error=None,
            environment=c.source.facts.baseline_inputs.environment,
            read_count=0,
            body_read_count=0,
            unique_objects=0,
        )
        return c.source.qualified

    monkeypatch.setattr(module, "qualify_admin_navigation_source", source)
    monkeypatch.setattr(module, "freeze_admin_execution_inputs", lambda *a, **k: frozen)
    monkeypatch.setattr(
        module, "prepare_admin_execution_configuration", lambda *a, **k: cast(Any, None)
    )

    def claim(*args: Any, **kw: Any) -> Any:
        events.append("original-claim")
        if state.fault == "claim":
            raise OSError("claim unconfirmed")
        return a["member"]

    monkeypatch.setattr(module, "admit_admin_production_member", claim)
    original = execute_claimed_admin_member

    def member(*args: Any, **kw: Any) -> Any:
        events.append("member")
        return original(*args, **kw)

    monkeypatch.setattr(module, "execute_claimed_admin_member", member)

    class Review:
        def __init__(self, **kw: Any) -> None:
            pass

        def run(self, *args: Any, **kw: Any) -> Any:
            events.append("independent-review")
            assert model_events[-2:] == ["model-close", "review-inputs"]
            body = {
                "passed": True,
                "business_result": result.evaluation.status,
                "generations": result.generations,
                "interactions": result.interactions,
            }
            if state.fault == "review":
                body["interactions"] = 999
            return SimpleNamespace(
                complete=True,
                returncode=0,
                stdout=json.dumps(body).encode(),
                stderr=b"",
            )

    monkeypatch.setattr(module, "ProcessRunner", Review)
    return selected, r, events, state, result, model_events


def test_source_before_claim_then_original_model_close_before_independent_review(
    entry: Any,
) -> None:
    selected, r, events, _, expected, _ = entry
    facts = execute_admin_navigation(selected, r)
    assert events == [
        "runtime-check",
        "actor-inputs",
        "source-declaration",
        "qualify-source",
        "execution-declaration",
        "original-claim",
        "member",
        "independent-review",
    ]
    assert facts["result"] == expected.model_dump(mode="json")
    assert facts["phase"] == "member_closed_reviewed"
    assert facts["formal_training_qualification"] is False
    assert facts["actual_actor_members_executed"] == []


@pytest.mark.parametrize("fault", ["source", "claim"])
def test_failed_source_or_claim_never_enters_model_or_member(
    entry: Any, fault: str
) -> None:
    selected, r, events, state, _, models = entry
    state.fault = fault
    with pytest.raises(OSError) as caught:
        execute_admin_navigation(selected, r)
    assert "member" not in events and models == []
    assert (
        getattr(caught.value, "admin_entry_facts")["business_result"] == "not_executed"
    )


def test_independent_disagreement_preserves_original_result(entry: Any) -> None:
    selected, r, _, state, expected, _ = entry
    state.fault = "review"
    with pytest.raises(ValueError, match="judgment/counters") as caught:
        execute_admin_navigation(selected, r)
    facts = getattr(caught.value, "admin_entry_facts")
    assert facts["result"] == expected.model_dump(mode="json")
    assert facts["independent_review"] == "not_completed"


def test_existing_source_entry_consumes_artifact_without_constructing_state_reader(
    entry: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected, runtime, events, state, expected, _ = entry

    def unexpected(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Existing source must not create a native state reader")

    monkeypatch.setattr(module, "SupervisedStateChecks", unexpected)
    declared = (
        state.qualified_source.material.site.configuration.admin_navigation_inputs
    )
    assert declared is not None
    runtime = replace(
        runtime,
        source_material=state.qualified_source.material,
        origin=AdminNavigationOrigin(endpoint=declared.origin.endpoint),
    )
    facts = execute_admin_navigation(selected, runtime)
    assert facts["result"] == expected.model_dump(mode="json")
    assert (
        facts["source_qualification_mode"] == "consume_existing_qualified_task_source"
    )
    assert facts["source_new_native_operations"] == 0
    assert "source-declaration" not in events and "qualify-source" not in events
    assert "original-claim" in events and "member" in events


def test_supplier_verified_source_bodies_reach_entry_without_second_graph_read(
    entry: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected, runtime, events, state, expected, _ = entry
    qualified = state.qualified_source
    declared = qualified.material.site.configuration.admin_navigation_inputs
    assert declared is not None
    runtime = replace(
        runtime,
        source_material=qualified.material,
        prevalidated_source=qualified,
        origin=AdminNavigationOrigin(endpoint=declared.origin.endpoint),
    )

    def unexpected(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Supplier verified this same-call source graph already")

    monkeypatch.setattr(module, "consume_admin_navigation_source", unexpected)
    monkeypatch.setattr(module, "SupervisedStateChecks", unexpected)
    facts = execute_admin_navigation(selected, runtime)
    assert facts["result"] == expected.model_dump(mode="json")
    assert (
        facts["source_qualification_mode"] == "consume_existing_qualified_task_source"
    )
    assert facts["source_new_native_operations"] == 0
    assert "source-declaration" not in events and "qualify-source" not in events
    assert "original-claim" in events and "member" in events


def test_later_actor_input_failure_keeps_supplier_source_checkpoint(
    entry: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected, runtime, events, state, _, _ = entry
    qualified = state.qualified_source
    runtime = replace(
        runtime, source_material=qualified.material, prevalidated_source=qualified
    )
    failure = OSError("unit actor input publication failure after source proof")

    def failed(*args: Any, **kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(module, "publish_known_actor_inputs", failed)
    with pytest.raises(OSError) as caught:
        execute_admin_navigation(selected, runtime)
    assert caught.value is failure
    facts = getattr(caught.value, "admin_entry_facts")
    assert facts["source_qualified"] is True
    assert facts[
        "closed_source_context_ref"
    ] == qualified.material.context_ref.model_dump(mode="json")
    assert facts["actual_actor_members_executed"] == []
    assert "original-claim" not in events and "source-declaration" not in events
