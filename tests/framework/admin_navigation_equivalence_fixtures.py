"""Linked synthetic source/candidate graphs with actual CAS and tree snapshots.

Native service replies and Reset facts are explicit fixtures. No physical source
authority, website, claim or permission is produced by this helper.
"""

from pathlib import Path
from typing import Any
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.reset import ResetInputs, assemble_reset
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from evidence_control_fixtures import EvidenceFixtureStore
from preparation_record_fixtures import put
from context_contract_fixtures import candidate_inputs
from state_contract_fixtures import baseline_inputs, reset_inputs, checks, op
from admin_navigation_fixtures import case, request
from test_slurm_commands import guard


def baseline(
    root: Path, store: EvidenceFixtureStore, contracts: Any, *, candidate: bool = False
) -> BaselineInputs:
    old = candidate_inputs() if candidate else baseline_inputs()
    public: PublicTask = contracts[0][2]
    spec = navigation_initial_state_spec(public.identity)
    spec_ref = put(store, spec)
    scope = old.prepared.scope.model_copy(update={"task": public.identity})
    private = bind_admin_navigation(*contracts[0]).private_spec
    binding = old.binding.model_copy(
        update={
            "identity": public.identity,
            "public_task_ref": put(store, public, "public"),
            "private_spec_ref": put(store, private),
            "baseline_ref": spec_ref,
        }
    )
    binding_ref = put(store, binding)
    worker, _ = case(root)
    current = request(contracts)
    current = current.model_copy(
        update={
            "binding_ref": binding_ref,
            "operation": current.operation.model_copy(
                update={
                    "run_id": scope.owner.run_id,
                    "owner_id": scope.owner.owner_id,
                    "attempt_id": scope.attempt_id,
                }
            ),
        }
    )
    worker.execute_task(current, control=guard())
    assert worker.snapshot is not None
    snapshot_ref = put(store, worker.snapshot)
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
    checked = checks(spec.environment_checks)
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
            "measured_state_sha256": worker.snapshot.state.digest,
        }
    )
    environment_ref = put(store, environment)
    preparation = old.preparation.model_copy(
        update={
            "scope": scope,
            "task_binding_ref": binding_ref,
            "spec_ref": spec_ref,
            "environment_ref": environment_ref,
            "checks": checks(spec.preparation_checks),
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
            "checks": checks(spec.initial_checks),
        }
    )
    value = BaselineInputs(
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
    # Validate all baseline joins before using the fixture in any comparison.
    assemble_baseline(
        value,
        old.initial.operation.model_copy(update={"operation_id": "baseline-fixture"}),
    )
    return value


def source(inputs: BaselineInputs, store: EvidenceFixtureStore) -> PublicContextInputs:
    old = reset_inputs()
    spec, scope = inputs.spec, inputs.prepared.scope
    task = old.task_recovery.model_copy(
        update={
            "baseline_ref": inputs.spec_ref,
            "state_coverage": spec.task_reset_checks,
        }
    )
    environment = old.environment_recovery.model_copy(
        update={
            "baseline_ref": inputs.spec_ref,
            "state_coverage": spec.environment_reset_checks,
        }
    )
    task_ref, environment_ref = put(store, task), put(store, environment)
    tokens = tuple(
        t.model_copy(update={"recovery_ref": task_ref})
        for t in old.plan.attempt_allocations
    )
    closures = tuple(
        c.model_copy(update={"token": t})
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
            "operation": old.task.operation.model_copy(
                update={"recovery_ref": task_ref}
            ),
            "recovery_ref": task_ref,
            "after_closure_refs": closure_refs,
            "checks": checks(spec.task_reset_checks),
        }
    )
    task_reset_ref = put(store, task_reset)
    env_reset = old.environment.model_copy(
        update={
            "scope": scope,
            "operation": old.environment.operation.model_copy(
                update={"recovery_ref": environment_ref}
            ),
            "recovery_ref": environment_ref,
            "after_task_reset_ref": task_reset_ref,
            "checks": checks(spec.environment_reset_checks),
        }
    )
    env_reset_ref = put(store, env_reset)
    health = old.health.model_copy(
        update={
            "scope": scope,
            "after_environment_reset_ref": env_reset_ref,
            "checks": checks(spec.health_checks),
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
    reset = assemble_reset(restoration, op("reset-fixture", cleanup=True))
    original = assemble_baseline(inputs, op("baseline-fixture"))
    context = PublicConstructionContext(
        context_id=scope.context_id,
        task=inputs.public_task,
        initial_observation_ref=inputs.observation_ref,
    )
    return PublicContextInputs(
        context=context,
        context_ref=put(store, context, "public"),
        baseline_inputs=inputs,
        baseline=original,
        baseline_ref=put(store, original),
        reset_inputs=restoration,
        reset=reset,
        reset_ref=put(store, reset),
    )
