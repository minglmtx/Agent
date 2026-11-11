"""Linked native-producer/domain-consumer graphs; service/rights remain doubles."""

import hashlib
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    assemble_public_context,
)
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.reset import ResetInputs, assemble_reset
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from evidence_control_fixtures import EvidenceFixtureStore
from preparation_record_fixtures import put
from context_contract_fixtures import candidate_inputs
from state_contract_fixtures import baseline_inputs, reset_inputs, checks, op, recovery
from shopping_category_native_fixtures import worker, request
from test_slurm_commands import guard
from test_shopping_category_navigation_input import reference
from retrieval_fixtures import reference as durable_reference


def baseline(
    root: Path,
    store: EvidenceFixtureStore,
    original: Any,
    *,
    candidate: bool = False,
    scope_override: StateScope | None = None,
) -> BaselineInputs:
    raw, _, public = original
    old = candidate_inputs() if candidate else baseline_inputs()
    from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
        category_navigation_initial_spec,
    )

    spec = category_navigation_initial_spec(public.identity)
    spec_ref = put(store, spec)
    scope = (
        old.prepared.scope.model_copy(update={"task": public.identity})
        if scope_override is None
        else StateScope.model_validate(scope_override)
    )
    assert scope.task == public.identity

    def original_operation(value: Any) -> Any:
        return (
            value
            if scope_override is None
            else value.model_copy(
                update={
                    "run_id": scope.owner.run_id,
                    "owner_id": scope.owner.owner_id,
                    "attempt_id": scope.attempt_id,
                    "operation_id": "historical-category-" + value.operation_id,
                }
            )
        )

    def original_checks(names: tuple[str, ...]) -> Any:
        result = checks(names)
        if scope_override is not None:
            proof = durable_reference(
                {"synthetic_historical_measurement": names}, store=store
            )
            result = result.model_copy(
                update={
                    "checks": tuple(
                        c.model_copy(update={"evidence": (proof,)})
                        for c in result.checks
                    )
                }
            )
        return result

    private = load_category_navigation_inputs(raw, reference(raw), public).private_spec
    binding = old.binding.model_copy(
        update={
            "identity": public.identity,
            "public_task_ref": put(store, public, "public"),
            "private_spec_ref": put(store, private),
            "baseline_ref": spec_ref,
        }
    )
    binding_ref = put(store, binding)
    task_plan = recovery(True).model_copy(
        update={
            "owner": scope.owner,
            "attempt_id": scope.attempt_id,
            "baseline_ref": spec_ref,
            "state_coverage": spec.task_reset_checks,
        }
    )
    env_plan = recovery(False).model_copy(
        update={
            "owner": scope.owner,
            "baseline_ref": spec_ref,
            "state_coverage": spec.environment_reset_checks,
        }
    )
    task_ref, env_ref = put(store, task_plan), put(store, env_plan)
    w, _ = worker(root)
    current = request(raw, public).model_copy(
        update={
            "binding_ref": binding_ref,
            "operation": request(raw, public).operation.model_copy(
                update={
                    "run_id": scope.owner.run_id,
                    "owner_id": scope.owner.owner_id,
                    "attempt_id": scope.attempt_id,
                    "allocation_id": old.environment.allocation.allocation_id,
                    "recovery_ref": task_ref,
                }
            ),
        }
    )
    w.execute_task(current, control=guard(60))
    assert w.tasks is not None and w.tasks.snapshot is not None
    saved = w.tasks.snapshot
    snapshot_ref = put(store, saved)
    selection = EnvironmentSelection(
        scope=scope,
        spec_ref=spec_ref,
        site_spec_ref=snapshot_ref.model_copy(
            update={"content_schema": "site-resource-spec/1"}
        ),
        site_started_ref=snapshot_ref.model_copy(
            update={"content_schema": "site-resource-started/1"}
        ),
        snapshot_ref=snapshot_ref,
    )
    selection_ref = put(store, selection)
    checked = original_checks(spec.environment_checks)
    checked = checked.model_copy(
        update={
            "checks": tuple(
                c.model_copy(update={"evidence": (selection_ref, snapshot_ref)})
                for c in checked.checks
            )
        }
    )
    environment = old.environment.model_copy(
        update={
            "scope": scope,
            "spec_ref": spec_ref,
            "checks": checked,
            "measured_state_sha256": hashlib.sha256(
                saved.state.model_dump_json().encode()
            ).hexdigest(),
            "allocation": old.environment.allocation.model_copy(
                update={"recovery_ref": env_ref, "owner": scope.owner}
            ),
            "operation": original_operation(old.environment.operation).model_copy(
                update={"recovery_ref": env_ref}
            ),
        }
    )
    environment_ref = put(store, environment)
    preparation = old.preparation.model_copy(
        update={
            "scope": scope,
            "task_binding_ref": binding_ref,
            "spec_ref": spec_ref,
            "environment_ref": environment_ref,
            "recovery_ref": task_ref,
            "operation": original_operation(old.preparation.operation).model_copy(
                update={"recovery_ref": task_ref}
            ),
            "checks": original_checks(spec.preparation_checks),
        }
    )
    preparation_ref = put(store, preparation)
    prepared = old.prepared.model_copy(
        update={
            "scope": scope,
            "public_task": public,
            "task_binding_ref": binding_ref,
            "spec_ref": spec_ref,
            "preparation_ref": preparation_ref,
            "private_checks_ref": binding.private_spec_ref,
            "recovery_ref": task_ref,
        }
    )
    prepared_ref = put(store, prepared)
    observed = old.observation.model_copy(
        update={
            "task": public.identity,
            "sequence": 0,
            "state": "ready",
            "context_id": scope.context_id,
            "attempt_id": scope.attempt_id,
            "tabs": (
                old.observation.tabs[0].model_copy(update={"url": public.start_url}),
            ),
        }
    )
    observed_ref = put(store, observed, "public")
    initial = old.initial.model_copy(
        update={
            "scope": scope,
            "spec_ref": spec_ref,
            "prepared_ref": prepared_ref,
            "observation_ref": observed_ref,
            "operation": original_operation(old.initial.operation),
            "checks": original_checks(spec.initial_checks),
        }
    )
    result = BaselineInputs(
        binding=binding,
        public_task=public,
        spec=spec,
        spec_ref=spec_ref,
        environment=environment,
        environment_ref=environment_ref,
        preparation=preparation,
        preparation_ref=preparation_ref,
        prepared=prepared,
        prepared_ref=prepared_ref,
        observation=observed,
        observation_ref=observed_ref,
        initial=initial,
        initial_ref=put(store, initial),
    )
    assemble_baseline(
        result,
        original_operation(
            old.initial.operation.model_copy(
                update={"operation_id": "baseline-fixture"}
            )
        ),
    )
    return result


def source(
    inputs: BaselineInputs, store: EvidenceFixtureStore, *, scoped: bool = False
) -> PublicContextInputs:
    old = reset_inputs()
    spec, scope = inputs.spec, inputs.prepared.scope

    def original_operation(value: Any) -> Any:
        return (
            value
            if not scoped
            else value.model_copy(
                update={
                    "run_id": scope.owner.run_id,
                    "owner_id": scope.owner.owner_id,
                    "attempt_id": scope.attempt_id,
                    "operation_id": "historical-category-" + value.operation_id,
                }
            )
        )

    def original_checks(names: tuple[str, ...]) -> Any:
        result = checks(names)
        if scoped:
            proof = durable_reference(
                {"synthetic_historical_reset": names}, store=store
            )
            result = result.model_copy(
                update={
                    "checks": tuple(
                        c.model_copy(update={"evidence": (proof,)})
                        for c in result.checks
                    )
                }
            )
        return result

    task_ref, environment_ref = (
        inputs.prepared.recovery_ref,
        inputs.environment.allocation.recovery_ref,
    )
    task = RecoveryPlan.model_validate_json(store.read(task_ref, control=guard()))
    environment = RecoveryPlan.model_validate_json(
        store.read(environment_ref, control=guard())
    )
    tokens = tuple(
        t.model_copy(
            update={
                "recovery_ref": task_ref,
                **(
                    {"owner": scope.owner, "attempt_id": scope.attempt_id}
                    if scoped
                    else {}
                ),
            }
        )
        for t in old.plan.attempt_allocations
    )
    closure_proof = (
        durable_reference({"synthetic_historical_close_only": True}, store=store)
        if scoped
        else None
    )
    closures = tuple(
        c.model_copy(
            update={"token": t, **({"evidence": (closure_proof,)} if scoped else {})}
        )
        for c, t in zip(old.closures, tokens, strict=True)
    )
    closure_refs = tuple(put(store, c) for c in closures)
    plan = old.plan.model_copy(
        update={
            "scope": scope,
            "spec_ref": inputs.spec_ref,
            "task_recovery_ref": task_ref,
            "environment_recovery_ref": environment_ref,
            "attempt_allocations": tokens,
        }
    )
    task_reset = old.task.model_copy(
        update={
            "scope": scope,
            "operation": original_operation(old.task.operation).model_copy(
                update={"recovery_ref": task_ref}
            ),
            "recovery_ref": task_ref,
            "after_closure_refs": closure_refs,
            "checks": original_checks(spec.task_reset_checks),
        }
    )
    task_reset_ref = put(store, task_reset)
    env_reset = old.environment.model_copy(
        update={
            "scope": scope,
            "operation": original_operation(old.environment.operation).model_copy(
                update={"recovery_ref": environment_ref}
            ),
            "recovery_ref": environment_ref,
            "after_task_reset_ref": task_reset_ref,
            "checks": original_checks(spec.environment_reset_checks),
        }
    )
    env_reset_ref = put(store, env_reset)
    health = old.health.model_copy(
        update={
            "scope": scope,
            "after_environment_reset_ref": env_reset_ref,
            "checks": original_checks(spec.health_checks),
            "operation": original_operation(old.health.operation),
        }
    )
    restoration = ResetInputs(
        plan=plan,
        plan_ref=put(store, plan),
        spec=spec,
        task_recovery=task,
        environment_recovery=environment,
        closures=closures,
        closure_refs=closure_refs,
        task=task_reset,
        task_ref=task_reset_ref,
        environment=env_reset,
        environment_ref=env_reset_ref,
        health=health,
        health_ref=put(store, health),
    )
    reset = assemble_reset(
        restoration, original_operation(op("source-reset", cleanup=True))
    )
    ready = assemble_baseline(inputs, original_operation(op("source-baseline")))
    context = PublicConstructionContext(
        context_id=scope.context_id,
        task=inputs.public_task,
        initial_observation_ref=inputs.observation_ref,
    )
    result = PublicContextInputs(
        context=context,
        context_ref=put(store, context, "public"),
        baseline_inputs=inputs,
        baseline=ready,
        baseline_ref=put(store, ready),
        reset_inputs=restoration,
        reset=reset,
        reset_ref=put(store, reset),
    )
    # Validate full joins, including recovery refs. Synthetic Reset/permissions
    # are explicit premises, never an actual physical/source qualification.
    freeze = original_operation(op("source-freeze")).model_copy(
        update={"attempt_id": None, "allocation_id": None, "recovery_ref": None}
    )
    assemble_public_context(result, freeze)
    return result
