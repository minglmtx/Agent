"""Freeze one category execution run on original task/context and Actor inputs."""

import json
from dataclasses import dataclass
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.optional_policies import InactivePolicy, RunPolicies
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RunResources,
    RoleModelPlan,
    ExecutionWorkload,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.policies.publication_inputs import checked_publication_inputs
from .shopping_category_actor_configuration import (
    CategoryNavigationActorInputs,
    category_actor_metadata,
    declare_category_actor_inputs,
)
from .shopping_category_source_publication import PublishedCategoryNavigationSource


@dataclass(frozen=True)
class FrozenCategoryNavigationRun:
    run: RunPlan
    binding: RunBinding
    task: TaskBinding
    inputs: ExecutionTaskInputs


def freeze_category_execution_run(
    source: PublishedCategoryNavigationSource,
    scope: StateScope,
    actor: ActorResourceSpec,
    parameters: LocalActorParameters,
    actor_inputs: CategoryNavigationActorInputs,
    operation: OperationContext,
    *,
    owner: OriginalSourceQualificationOwner,
    evidence: EvidenceStore,
    controls: OperationControls,
    task_seconds: int,
    cleanup_seconds: int,
) -> FrozenCategoryNavigationRun:
    if (
        not isinstance(source, PublishedCategoryNavigationSource)
        or not isinstance(actor_inputs, CategoryNavigationActorInputs)
        or not isinstance(owner, OriginalSourceQualificationOwner)
    ):
        raise TypeError("Actual category source and exact frozen Actor inputs required")
    scope = StateScope.model_validate(scope)
    actor = ActorResourceSpec.model_validate(actor)
    parameters = LocalActorParameters.model_validate(parameters)
    operation = OperationContext.model_validate(operation)
    if (
        type(task_seconds) is not int
        or type(cleanup_seconds) is not int
        or not 1 <= task_seconds <= 14400
        or not 1 <= cleanup_seconds <= 3600
    ):
        raise ValueError("Explicit bounded category execution/cleanup budgets required")
    checked = checked_publication_inputs(
        source.material.context_ref, source.receipt, source.inputs
    )
    baseline = checked.baseline_inputs
    installation = source.material.site.configuration.installation
    context, policy = actor_inputs.context, actor_inputs.policy
    expected = declare_category_actor_inputs(
        actor.artifact,
        actor.engine_config,
        actor_inputs.binding,
        actor.model_binding_ref,
        parameters,
        context.policy.software_evidence_ref,
        actor_inputs.software,
    )
    if (
        expected != actor_inputs
        or owner.scope != source.receipt.scope
        or owner.evidence is not evidence
        or source.receipt.scope.owner != scope.owner
        or source.receipt.scope.task != scope.task
        or source.receipt.scope.attempt_id == scope.attempt_id
        or source.receipt.scope.context_id == scope.context_id
        or baseline.binding.identity != scope.task
        or actor.token.owner != scope.owner
        or actor.release_ref != installation.manifest_ref
        or actor_inputs.binding.release_ref != actor.release_ref
        or actor.python_executable != installation.python_executable
        or len(
            [
                declared
                for declared in installation.manifest.artifacts
                if declared.artifact_id == actor.artifact.artifact_id
                and declared.files == actor.artifact.files
            ]
        )
        != 1
        or (
            operation.run_id,
            operation.owner_id,
            operation.mode,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
        )
        != (scope.owner.run_id, scope.owner.owner_id, "execute", None, None, None)
        or (
            actor.engine_config.context_window,
            parameters.max_input_tokens,
            parameters.max_new_tokens,
        )
        != (65536, 61440, 4096)
        or len(context.profiles) != 20
        or policy.max_generations != 20
        or policy.max_interactions != 16
        or any(
            p.routing_ref != actor.model_binding_ref
            or p.configuration_ref != actor_inputs.parameters_ref
            for p in context.profiles
        )
    ):
        raise OwnershipConflict(
            "Category run changed source/owner/release/Actor64 inputs"
        )
    require_complete_bytes(
        actor_inputs.parameters_ref, parameters.model_dump_json().encode()
    )
    require_complete_bytes(actor_inputs.context_ref, context.model_dump_json().encode())
    require_complete_bytes(
        actor_inputs.skill_ref, policy.skill.model_dump_json().encode()
    )
    if policy.actor_context_ref != actor_inputs.context_ref:
        raise OwnershipConflict(
            "Category Actor policy changed original context reference"
        )
    proposed: list[tuple[bytes, EvidenceRef]] = []

    def planned(raw: bytes, schema: str) -> EvidenceRef:
        ref = evidence_reference(raw, category_actor_metadata(schema))
        proposed.append((raw, ref))
        return ref

    split_ref = planned(
        json.dumps(
            {
                "schema_version": "engineering-source-split/1",
                "engineering_only": True,
                "formal_source_admission": False,
                "split": "train",
                "source_task_id": scope.task.source_task_id,
                "actual_qualified_source": source.material.context_ref.model_dump(
                    mode="json"
                ),
            },
            sort_keys=True,
        ).encode(),
        "engineering-source-split/1",
    )
    task_ref = planned(
        json.dumps(
            {
                "schema_version": "engineering-task-manifest/1",
                "bindings": [
                    baseline.prepared.task_binding_ref.model_dump(mode="json")
                ],
            },
            sort_keys=True,
        ).encode(),
        "engineering-task-manifest/1",
    )
    inputs = ExecutionTaskInputs(
        task_binding_ref=baseline.prepared.task_binding_ref,
        source_context_receipt_ref=source.material.context_ref,
        skill_ref=actor_inputs.skill_ref,
        attempt_id=scope.attempt_id,
    )
    run = RunPlan(
        run_id=scope.owner.run_id,
        release_ref=actor.release_ref,
        purpose="engineering",
        split="train",
        split_manifest_ref=split_ref,
        task_manifest_ref=task_ref,
        tasks=(baseline.binding,),
        workload=ExecutionWorkload(
            execution_policy_ref=planned(
                policy.model_dump_json().encode(), policy.schema_version
            ),
            task_inputs_ref=planned(
                inputs.model_dump_json().encode(), inputs.schema_version
            ),
            seed=parameters.seed,
        ),
        policies=RunPolicies(
            actor_memory=policy.memory,
            teacher_template=InactivePolicy(
                status="not_applicable",
                reason="Unpaid single Actor execution; no construction or Teacher dispatch",
            ),
        ),
        models=(
            RoleModelPlan(
                role="actor",
                provider="fixed-actor-worker",
                model=context.profiles[0].model,
                model_binding_ref=actor.model_binding_ref,
                parameters_ref=actor_inputs.parameters_ref,
                paid=False,
            ),
        ),
        resources=RunResources(
            configuration_ref=planned(
                actor.model_dump_json().encode(), actor.schema_version
            ),
            max_parallel_tasks=1,
            max_actor_generations_per_attempt=20,
            max_interactions_per_attempt=16,
            operation_timeout_seconds=task_seconds,
            cleanup_timeout_seconds=cleanup_seconds,
        ),
        run_capacity=JournalCapacity(
            max_attempts=1,
            max_entries=128,
            max_bytes=8 * 1024**2,
            max_entry_bytes=65536,
        ),
        budget=None,
    )
    from lab_generate_skill.domain.evidence import EvidenceMetadata

    plan_ref = evidence_reference(
        run.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=run.schema_version,
            visibility="private",
            producer="run-plans-v1",
        ),
    )
    binding = RunBinding(
        owner=scope.owner,
        plan_ref=plan_ref,
        release_ref=run.release_ref,
        submission_key="shopping-category-"
        + scope.owner.job_id
        + "-"
        + scope.task.source_task_id,
    )
    control = controls.bind(operation)
    owner.require(operation, control, new_work=False)
    source.contexts.check_context_current(operation, control)
    known: list[EvidenceRef] = []
    try:
        for raw, ref in proposed:
            metadata = EvidenceMetadata.model_validate(
                ref.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            )
            current = evidence.put(raw, metadata, control=control)
            known.append(current)
            if current != ref:
                raise OwnershipConflict(
                    "Category run input publication changed exact reference"
                )
        source.contexts.check_context_current(operation, control)
        owner.require(operation, control, new_work=False)
        control.checkpoint()
    except BaseException as error:
        setattr(error, "category_run_known_references", tuple(known))
        setattr(error, "category_run_candidates", tuple(ref for _, ref in proposed))
        raise
    return FrozenCategoryNavigationRun(run, binding, baseline.binding, inputs)
