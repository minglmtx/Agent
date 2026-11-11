"""Synthetic linked facts for pure context/comparison contracts; no authority."""

from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceChecks,
    EquivalenceInputs,
)
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    assemble_public_context,
)
from lab_generate_skill.domain.reset import assemble_reset
from retrieval_fixtures import reference
from state_contract_fixtures import baseline_inputs, reset_inputs, op, checks, recovery
from test_run_journal import command


def source_inputs(
    *, allowed_actions: tuple[str, ...] = ("stop",)
) -> PublicContextInputs:
    initial, restoration = (
        baseline_inputs(allowed_actions=allowed_actions),
        reset_inputs(),
    )
    baseline = assemble_baseline(initial, op("source-baseline"))
    reset = assemble_reset(restoration, op("source-reset", cleanup=True))
    context = PublicConstructionContext(
        context_id=baseline.scope.context_id,
        task=initial.public_task,
        initial_observation_ref=baseline.observation_ref,
    )
    return PublicContextInputs(
        context=context,
        context_ref=reference(context, context.schema_version, "public"),
        baseline_inputs=initial,
        baseline=baseline,
        baseline_ref=reference(baseline, baseline.schema_version),
        reset_inputs=restoration,
        reset=reset,
        reset_ref=reference(reset, reset.schema_version),
    )


def candidate_inputs(
    attempt_id: str = "candidate", *, allowed_actions: tuple[str, ...] = ("stop",)
) -> BaselineInputs:
    initial = baseline_inputs(allowed_actions=allowed_actions)
    scope = initial.prepared.scope.model_copy(
        update={
            "attempt_id": attempt_id,
            "context_id": "candidate-context",
        }
    )
    env = initial.environment.model_copy(
        update={
            "scope": scope,
            "operation": initial.environment.operation.model_copy(
                update={
                    "attempt_id": attempt_id,
                    "operation_id": "candidate-environment",
                }
            ),
        }
    )
    env_ref = reference(env, env.schema_version)
    task_recovery = recovery(True).model_copy(update={"attempt_id": attempt_id})
    recovery_ref = reference(task_recovery, task_recovery.schema_version)
    prep = initial.preparation.model_copy(
        update={
            "scope": scope,
            "environment_ref": env_ref,
            "recovery_ref": recovery_ref,
            "operation": initial.preparation.operation.model_copy(
                update={
                    "attempt_id": attempt_id,
                    "operation_id": "candidate-prepare",
                    "recovery_ref": recovery_ref,
                }
            ),
        }
    )
    prep_ref = reference(prep, prep.schema_version)
    prepared = initial.prepared.model_copy(
        update={
            "scope": scope,
            "preparation_ref": prep_ref,
            "recovery_ref": recovery_ref,
        }
    )
    prepared_ref = reference(prepared, prepared.schema_version)
    observation = initial.observation.model_copy(
        update={
            "observation_id": "candidate-observation",
            "context_id": scope.context_id,
            "attempt_id": scope.attempt_id,
            "text": "Equivalent view with a different timestamp",
        }
    )
    observed_ref = reference(observation, observation.schema_version, "public")
    measured = initial.initial.model_copy(
        update={
            "scope": scope,
            "prepared_ref": prepared_ref,
            "observation_ref": observed_ref,
            "measured_state_sha256": "9" * 64,
            "operation": initial.initial.operation.model_copy(
                update={"attempt_id": attempt_id, "operation_id": "candidate-initial"}
            ),
        }
    )
    return initial.model_copy(
        update={
            "environment": env,
            "environment_ref": env_ref,
            "preparation": prep,
            "preparation_ref": prep_ref,
            "prepared": prepared,
            "prepared_ref": prepared_ref,
            "observation": observation,
            "observation_ref": observed_ref,
            "initial": measured,
            "initial_ref": reference(measured, measured.schema_version),
        }
    )


def equivalence_inputs(
    *, allowed_actions: tuple[str, ...] = ("stop",)
) -> EquivalenceInputs:
    source = source_inputs(allowed_actions=allowed_actions)
    frozen = assemble_public_context(source, command("freeze"))
    source_ref = reference(frozen, frozen.schema_version)
    candidate = candidate_inputs(allowed_actions=allowed_actions)
    baseline = assemble_baseline(
        candidate, command("candidate-baseline", attempt="candidate")
    )
    baseline_ref = reference(baseline, baseline.schema_version)
    comparison = EquivalenceChecks(
        scope=baseline.scope,
        operation=command("compare", attempt="candidate"),
        source_context_receipt_ref=source_ref,
        candidate_baseline_ref=baseline_ref,
        checks=checks(frozen.equivalence_scope),
    )
    return EquivalenceInputs(
        source_inputs=source,
        source=frozen,
        source_ref=source_ref,
        candidate_inputs=candidate,
        candidate=baseline,
        candidate_ref=baseline_ref,
        checks=comparison,
        checks_ref=reference(comparison, comparison.schema_version),
    )
