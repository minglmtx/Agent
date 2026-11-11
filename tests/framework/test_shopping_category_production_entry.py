"""Actual source producer→entry→claim/phase/run consumers, with no site/model start."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
import json
import os
import pytest
from lab_generate_skill.bootstrap.shopping_category_production_entry import (
    CategoryNavigationProductionRuntime,
    run_category_production,
)
from lab_generate_skill.bootstrap.shopping_category_production_review import review
from lab_generate_skill.bootstrap.member_metadata import finish_member_metadata
from lab_generate_skill.bootstrap.shopping_category_actor_configuration import (
    category_actor_metadata,
)
from lab_generate_skill.domain.operation_window import OperationTimeWindow
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from shopping_category_run_fixtures import run_input_case, W
from shopping_category_owned_reads import CategoryUnitRead
from test_shopping_category_navigation_input import originals as originals, reference
from site_instance_fixtures import node_path as node_path
import lab_generate_skill.bootstrap.shopping_category_production_entry as entry


def runtime_case(
    tmp_path: Path, node_path: Path, patch: pytest.MonkeyPatch, original: Any
) -> Any:
    c = run_input_case(tmp_path, node_path, patch, original)
    s = c.source
    clock = s.site.clock
    control = BoundedOperationControls(
        c.controls,
        clock,
        OperationTimeWindow(
            owner=c.scope.owner,
            execution_deadline=c.operation.deadline,
            cleanup_deadline=c.operation.deadline + timedelta(seconds=100),
            hard_end=c.operation.deadline + timedelta(seconds=200),
        ),
    )
    source_reads = CategoryUnitRead(s, tmp_path / "source/evidence", c.operation)
    (tmp_path / "run").mkdir()
    (tmp_path / "claims").mkdir()
    spec = c.published.material.site
    origin = spec.configuration.shopping_category_inputs.origin
    accounting = c.store.put(
        b"{}", category_actor_metadata("original-slurm-accounting/1")
    )
    model_op = c.operation.model_copy(
        update={
            "operation_id": "actor.model.acquire",
            "allocation_id": c.actor.token.allocation_id,
            "recovery_ref": c.actor.token.recovery_ref,
        }
    )
    from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets

    budgets = SourceRecoveryBudgets.model_validate_json(
        (
            W
            / "experiments/framework-map-navigation42-production-20261102-v1/runtime-source-consumption-candidate/source-recovery-budgets.json"
        ).read_bytes()
    )
    c.runtime = CategoryNavigationProductionRuntime(
        s.owner,
        c.scope,
        c.operation,
        c.actor,
        model_op,
        c.binding,
        c.parameters,
        c.software_ref,
        c.software,
        c.published.material.browser.configuration,
        s.assets,
        source_reads,
        s.site.journal,
        control,
        clock,
        cast(Any, None),
        tmp_path,
        tmp_path,
        node_path / "unused-source",
        node_path / "entry-candidate",
        tmp_path / "claims",
        "category-production-entry-unit",
        origin,
        accounting,
        spec.configuration.files.image,
        Path(spec.configuration.files.source_path),
        120,
        120,
        1,
        120,
        60,
        60,
        10,
        10,
        60,
        budgets,
        c.published.material,
        c.published,
    )
    return c


@pytest.mark.parametrize("windows", ["legacy", "selected", "selected-retention"])
@pytest.mark.parametrize("binding", ["legacy", "deferred-retained", "deferred-new"])
def test_real_entry_reuses_original_bodies_then_reaches_claimed_phase_consumer(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    binding: str,
    windows: str,
) -> None:
    c = runtime_case(tmp_path, node_path, monkeypatch, originals[0])
    from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets

    if windows != "legacy":
        c.runtime = replace(
            c.runtime,
            actor_cleanup_seconds=5,
            generation_budgets=ActorGenerationBudgets(
                preparation_seconds=10,
                execution_seconds=10,
                retention_seconds=10 if windows == "selected-retention" else None,
            ),
        )
    installation = c.published.material.browser.configuration.installation
    if binding != "legacy":
        c.runtime = replace(c.runtime, template=None, source_installation=installation)
    if binding == "deferred-new":
        from lab_generate_skill.adapters.slurm.source_qualification_owner import (
            OriginalSourceQualificationOwner,
        )

        # A new unit invocation starts before publication seals its owner.
        # Keep the fixture's completed source owner sealed and unchanged.
        prior = c.runtime.owner
        pending = OriginalSourceQualificationOwner(
            prior.scope, prior.execution, prior.controller, prior.evidence
        )
        c.runtime = replace(
            c.runtime, owner=pending, retained_source=None, verified_source=None
        )
    seen = []

    def no_rebuild(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("same-call source rebuilt/reread")

    monkeypatch.setattr(entry, "consume_category_navigation_source", no_rebuild)

    def qualification(*args: Any, **kwargs: Any) -> Any:
        # Source producer is exercised separately. Replace only its site effects
        # with that exact producer's qualified body, never placeholder refs.
        assert binding == "deferred-new"
        assert args[0] is c.runtime.owner
        assert args[1].configuration.installation == installation
        assert args[5] == c.published.inputs.context.task
        c.runtime.owner.seal(
            c.runtime.operation, c.runtime.controls.bind(c.runtime.operation)
        )
        return c.published

    monkeypatch.setattr(
        entry,
        "qualify_category_navigation_source",
        qualification if binding == "deferred-new" else no_rebuild,
    )

    class BeforeResourceStart(Exception):
        pass

    failure = BeforeResourceStart("unit stops before acquiring model/site")

    def stop(
        member: Any, source: Any, candidate: Any, *args: Any, **kwargs: Any
    ) -> Any:
        seen.append(member)
        assert source is c.published
        assert args[2] is c.published.material.browser.configuration
        assert args[3].generation_budgets == c.runtime.generation_budgets
        assert args[3].generation_seconds == c.runtime.generation_seconds
        assert candidate.spec.configuration.shopping_category_inputs.scope == c.scope
        assert candidate.deferred_acquisition is True
        assert member.owner.task_plan == member.declarations.plan
        assert (
            member.declarations.preparation.resource_read_operation.parent_operation_id
            == candidate.acquisition.operation_id
        )
        raise failure

    monkeypatch.setattr(entry, "execute_claimed_category_member", stop)
    facts: dict[str, Any] = {}
    with pytest.raises(BeforeResourceStart) as caught:
        run_category_production(
            c.runtime,
            originals[0][0],
            reference(originals[0][0]),
            c.published.inputs.context.task,
            facts,
        )
    assert caught.value is failure and len(seen) == 1
    assert facts["source_qualified"] is True and facts["source_qualification_mode"] == (
        "construct_task_specific_source"
        if binding == "deferred-new"
        else "consume_existing_qualified_task_source"
    )
    assert (
        facts["phase"] == "unified_task_lifecycle"
        and facts["actual_actor_members_executed"] == []
    )
    assert len(list((tmp_path / "claims").glob("*.json"))) == 1
    assert not (node_path / "entry-candidate").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "material",
        "body",
        "owner",
        "budget",
        "installation-missing",
        "installation-mismatch",
    ],
)
def test_entry_refuses_stale_or_wrong_source_and_limits_before_claim(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = runtime_case(tmp_path, node_path, monkeypatch, originals[0])
    r = c.runtime
    if fault == "material":
        r = replace(
            r,
            retained_source=r.retained_source.model_copy(
                update={"context_ref": r.accounting_ref}
            ),
        )
    elif fault == "body":
        r = replace(
            r,
            verified_source=replace(
                c.published,
                receipt=c.published.receipt.model_copy(update={"scope": c.scope}),
            ),
        )
    elif fault == "owner":
        r = replace(
            r,
            scope=c.scope.model_copy(
                update={
                    "task": c.scope.task.model_copy(
                        update={"source_task_id": "wrong-task"}
                    )
                }
            ),
        )
    elif fault == "budget":
        r = replace(r, site_seconds=True)
    elif fault == "installation-missing":
        r = replace(r, template=None)
    else:
        r = replace(
            r,
            source_installation=c.published.material.browser.configuration.installation.model_copy(
                update={"python_executable": "/anvme/workspace/other/bin/python"}
            ),
        )
    with pytest.raises(
        ValueError if fault in {"budget", "installation-missing"} else OwnershipConflict
    ):
        run_category_production(
            r,
            originals[0][0],
            reference(originals[0][0]),
            c.published.inputs.context.task,
            {},
        )
    assert not list((tmp_path / "claims").iterdir()) and not list(
        (tmp_path / "run").iterdir()
    )
    assert not (node_path / "entry-candidate").exists()


@pytest.mark.parametrize(
    "facts",
    [
        {},
        [],
        {
            "schema_version": "shopping-category-owned-closed-review-inputs/1",
            "original_process": os.getpid(),
            "engineering_only": True,
        },
    ],
)
def test_independent_review_rejects_missing_wrong_or_same_process_input(
    tmp_path: Path, facts: Any
) -> None:
    path = tmp_path / "review.json"
    path.write_text(json.dumps(facts))
    with pytest.raises(ValueError):
        review(path)


def test_metadata_finalization_keeps_original_and_revoke_failure_when_output_fails(
    tmp_path: Path,
) -> None:
    primary = ValueError("original")
    cleanup = RuntimeError("revoke")
    facts: dict[str, Any] = {}
    calls = []

    def revoke() -> None:
        calls.append("revoke")
        raise cleanup

    (tmp_path / "member-result.json").mkdir()
    with pytest.raises(BaseExceptionGroup) as caught:
        finish_member_metadata(tmp_path, facts, revoke, primary)
    assert (
        caught.value.exceptions[0] is primary and caught.value.exceptions[1] is cleanup
    )
    assert isinstance(caught.value.exceptions[2], IsADirectoryError)
    assert calls == ["revoke"] and facts["metadata_admission_revoked"] is False


@pytest.mark.parametrize("fault", ["bind", "cancel", "cancel-close", "returned-result"])
def test_claimed_member_closes_original_model_and_retains_partial_facts(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    # Actual source, claim, phase declarations and owned binding; only model
    # process and task effects are explicit unit premises. No Actor/native run.
    from contextlib import contextmanager
    from collections.abc import Iterator
    from lab_generate_skill.adapters.models.actor_execution_scope import (
        ActorExecutionScope,
    )
    from lab_generate_skill.domain.local_actor import LocalActorBinding
    from lab_generate_skill.domain.errors import OperationStopped
    from lab_generate_skill.domain.evaluation import Evaluation
    from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
    import lab_generate_skill.bootstrap.shopping_category_production_member as member_module

    c = runtime_case(tmp_path, node_path, monkeypatch, originals[0])
    captured = []
    calls = []
    bound = []

    class BeforeModel(Exception):
        pass

    def capture(*args: Any, **kwargs: Any) -> Any:
        captured.append((args, kwargs))
        raise BeforeModel()

    monkeypatch.setattr(entry, "execute_claimed_category_member", capture)
    with pytest.raises(BeforeModel):
        run_category_production(
            c.runtime,
            originals[0][0],
            reference(originals[0][0]),
            c.published.inputs.context.task,
            {},
        )
    args, kwargs = captured[0]
    member = args[0]
    primary = OperationStopped(
        "CANCELLED", member.declarations.plan.operation.operation_id
    )
    cleanup = RuntimeError("unit model-close failure")

    @contextmanager
    def model_scope(*args: Any, **kwargs: Any) -> Iterator[Any]:
        calls.append("acquire")
        try:
            yield object()
        except BaseException as error:
            if fault == "cancel-close":
                raise BaseExceptionGroup(
                    "unit primary and close", [error, cleanup]
                ) from None
            raise
        finally:
            calls.append("close")

    class UnitAcquiredScope(ActorExecutionScope):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.binding = LocalActorBinding(
                resource=c.actor.token,
                release_ref=c.actor.release_ref,
                model_binding_ref=c.actor.model_binding_ref,
                spec_ref=c.store.put(
                    c.actor.model_dump_json().encode(),
                    category_actor_metadata("actor-resource-spec/1"),
                ),
                acquired_ref=c.store.put(
                    b'{"explicit_unit_premise":true}',
                    category_actor_metadata("actor-resource-fact/1"),
                ),
                cleanup_seconds=60,
            )

    from lab_generate_skill.bootstrap.shopping_category_production_execution import (
        bind_category_production_execution as actual_bind,
    )

    returned = None
    if fault == "returned-result":
        eval_ref = c.store.put(
            member.declarations.plan.evaluation.model_dump_json().encode(),
            category_actor_metadata("evaluation-contract/1"),
        )
        evaluation = Evaluation(
            identity=c.scope.task,
            attempt_id=c.scope.attempt_id,
            contract_ref=eval_ref,
            evaluator_id="unit-partial",
            evaluator_version="1",
            status="unknown",
            reward=None,
            checks=(),
            reason_code="UNIT_PARTIAL",
        )
        returned = ExecutionTaskResult(
            intent=member.declarations.plan.intent,
            attempt_ref=c.store.put(
                b"{}", category_actor_metadata("execution-attempt-result/1")
            ),
            evaluation=evaluation,
            evaluation_ref=c.store.put(
                evaluation.model_dump_json().encode(),
                category_actor_metadata("evaluation/1"),
            ),
            generations=0,
            interactions=0,
        )

    def bind(*args: Any, **kwargs: Any) -> Any:
        if fault == "bind":
            raise primary
        owned = actual_bind(*args, **kwargs)
        bound.append(owned)

        def task(*args: Any, **kwargs: Any) -> Any:
            if returned is not None:
                return returned
            raise primary

        monkeypatch.setattr(owned.bundle.task, "execute", task)
        return owned

    monkeypatch.setattr(member_module, "claimed_actor_resource", model_scope)
    monkeypatch.setattr(member_module, "ActorExecutionScope", UnitAcquiredScope)
    monkeypatch.setattr(member_module, "bind_category_production_execution", bind)
    expected = (
        BaseExceptionGroup
        if fault == "cancel-close"
        else ValueError if fault == "returned-result" else OperationStopped
    )
    with pytest.raises(expected) as caught:
        member_module.execute_claimed_category_member(*args, **kwargs)
    assert calls == ["acquire", "close"]
    error = caught.value
    if fault == "cancel-close":
        assert isinstance(error, BaseExceptionGroup) and error.exceptions == (
            primary,
            cleanup,
        )
    elif fault != "returned-result":
        assert error is primary
    assert getattr(error, "category_original_member") is member
    assert getattr(error, "category_task_result") is returned
    assert getattr(error, "category_model_executions") == ()
    assert "model_acquisition" in getattr(error, "category_phase_seconds")
    for owned in bound:
        assert owned.resources.site.phase == "new" and owned.resources.browser() is None


@pytest.mark.parametrize("fault", ["image", "budget", "source-index"])
def test_supplier_refuses_wrong_image_or_budget_before_accounting_and_asset_staging(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    from lab_generate_skill.bootstrap.shopping_category_runtime_supply import (
        CategoryNavigationSupplierInputs,
        supply_category_runtime,
    )
    from lab_generate_skill.domain.operation_window import OperationWindowBudgets
    import lab_generate_skill.bootstrap.shopping_category_runtime_supply as supplier

    c = runtime_case(tmp_path, node_path, monkeypatch, originals[0])
    r = c.runtime
    selected = CategoryNavigationSupplierInputs(
        installation=r.declared_installation,
        binding=r.binding,
        engine=r.model.engine_config,
        parameters=r.parameters,
        software_ref=r.software_ref,
        software=r.software,
        browser_assets=r.browser_assets,
        image=r.image,
        image_source=r.image_source,
        origin=r.origin,
        job_budgets=OperationWindowBudgets(
            execution_seconds=2000,
            cleanup_seconds=1000,
            final_margin_seconds=100,
            stop_signal_lead_seconds=1100,
        ),
        recovery_budgets=r.source_recovery_budgets,
        site_seconds=r.site_seconds,
        task_seconds=r.task_seconds,
        setup_seconds=r.setup_seconds,
        source_metadata_seconds=r.source_metadata_seconds,
        metadata_cleanup_seconds=r.metadata_cleanup_seconds,
        physical_close_seconds=r.physical_close_seconds,
        generation_seconds=r.generation_seconds,
        interaction_seconds=r.interaction_seconds,
        actor_cleanup_seconds=r.actor_cleanup_seconds,
    )
    if fault == "source-index":
        from pydantic import TypeAdapter

        adapter = TypeAdapter(CategoryNavigationSupplierInputs)
        selected = adapter.validate_json(adapter.dump_json(selected, exclude_none=True))
        assert selected.template is None
    if fault == "image":
        selected = replace(
            selected, image=r.image.model_copy(update={"sha256": "0" * 64})
        )
    elif fault == "budget":
        selected = replace(selected, site_seconds=True)
    calls = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        calls.append("accounting/staging")
        pytest.fail("Wrong immutable input reached external work")

    monkeypatch.setattr(supplier, "original_execution", forbidden)
    monkeypatch.setattr(supplier, "copy_pinned_file", forbidden)
    with pytest.raises(
        ValueError, match="checkpoint index" if fault == "source-index" else None
    ):
        with supply_category_runtime(
            selected,
            originals[0][0],
            reference(originals[0][0]),
            c.published.inputs.context.task,
            tmp_path,
            tmp_path / "claims",
            claim_scope="unit",
            source_index=(
                None
                if fault == "source-index"
                else tmp_path / "original-index-not-read-before-input-refusal.json"
            ),
        ):
            pytest.fail("Invalid supplier was yielded")
    assert not calls and not (tmp_path / "member-result.json").exists()
