"""Actual selected inputs in an explicitly engineering, unpaid execution plan."""

from dataclasses import dataclass
import json
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.bootstrap.actor_context_runtime import freeze_actor_context
from lab_generate_skill.domain.actor_projection import (
    ActorProjectionConfiguration,
    FullAxProjection,
    actor_projection_configuration,
    check_projection_task,
)
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.execution import RunBinding, AttemptBinding
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RunResources,
    RoleModelPlan,
    ExecutionWorkload,
)
from lab_generate_skill.domain.optional_policies import RunPolicies, InactivePolicy
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.domain.evidence import EvidenceRef
from actor_resource_fixtures import ResourceCase as ActorCase
from browser_resource_fixtures import ResourceCase as BrowserCase
from actor_source_protocol import ActorSource
from test_actor_protocol import turn


@dataclass(frozen=True)
class SourceActorPlan:
    run: RunPlan
    trace: TracePlan
    request: ActorRunRequest
    projection: ActorProjectionConfiguration


def plan_source_actor(
    source: ActorSource,
    browser: BrowserCase,
    actor: ActorCase,
    initial: EvidenceRef,
    params: LocalActorParameters,
    *,
    max_interactions: int = 16,
    projection: ActorProjectionConfiguration | None = None,
    context_policy: ContextProjectionPolicy | None = None,
    context_soft_target: int = 24576,
) -> SourceActorPlan:
    if type(max_interactions) is not int or not 1 <= max_interactions <= 20:
        raise ValueError("Explicit engineering interaction limit must be integer1..20")
    choice = (
        FullAxProjection()
        if projection is None
        else actor_projection_configuration(projection)
    )
    check_projection_task(choice, source.native.public.identity)
    n = source.native
    assert n.request is not None and source.saved["baseline"].status == "ready"
    assert source.saved["baseline_inputs"].observation_ref == initial
    state = source.saved["baseline_inputs"].prepared.scope
    assert state.owner == actor.spec.token.owner == browser.spec.token.owner
    selected = turn()  # Same declared engineering skill/memory as prior GPU checks.
    params_ref = n.raw(params.model_dump_json().encode(), "model-parameters/1")
    publication_op = actor.op.model_copy(update={"operation_id": "source-actor-plan"})
    context = None
    context_ref = None
    candidate_id = "engineering-" + selected.skill.content_digest
    if context_policy is not None:
        context_policy = ContextProjectionPolicy.model_validate(context_policy)
        if (context_policy.actor_projection or FullAxProjection()) != choice:
            raise ValueError("Actor context and original page projection differ")
        context = freeze_actor_context(
            actor.spec,
            (params_ref,) * 20,
            context_policy,
            actor.evidence,
            soft_target=context_soft_target,
            control=actor.controls.bind(publication_op),
        )
        context_ref = n.put(context)
    inputs_ref = n.raw(
        json.dumps(
            dict(
                engineering_only=True,
                binding_ref=n.binding_ref.model_dump(mode="json"),
                baseline_ref=source.saved["baseline_ref"].model_dump(mode="json"),
                initial_observation_ref=initial.model_dump(mode="json"),
            )
        ).encode(),
        "engineering-source-inputs/1",
    )
    policy_ref = n.raw(
        json.dumps(
            dict(
                engineering_only=True,
                skill=selected.skill.model_dump(mode="json"),
                memory=selected.memory.model_dump(mode="json"),
                max_generations=20,
                max_interactions=max_interactions,
                **(
                    {"actor_projection": choice.model_dump(mode="json")}
                    if projection is not None
                    else {}
                ),
            )
        ).encode(),
        (
            "engineering-execution-policy/1"
            if projection is None
            else "engineering-execution-policy/2"
        ),
    )
    if context_ref is not None:
        policy_ref = n.put(
            EngineeringActorPolicy(
                skill=selected.skill,
                memory=selected.memory,
                max_generations=20,
                max_interactions=max_interactions,
                actor_projection=choice,
                actor_context_ref=context_ref,
                candidate_id=candidate_id,
                revision_round=0,
            )
        )
    split_ref = n.raw(
        json.dumps(
            dict(
                engineering_only=True,
                formal_source_admission=False,
                split=n.public.identity.split,
                source_task_id=n.public.identity.source_task_id,
                native_contract_ref=n.native_contract_ref.model_dump(mode="json"),
            )
        ).encode(),
        "engineering-source-split/1",
    )
    task_ref = n.raw(
        json.dumps(
            dict(
                engineering_only=True, bindings=[n.binding_ref.model_dump(mode="json")]
            )
        ).encode(),
        "engineering-task-manifest/1",
    )
    run = RunPlan(
        run_id=state.owner.run_id,
        release_ref=actor.spec.release_ref,
        purpose="engineering",
        split=n.public.identity.split,
        split_manifest_ref=split_ref,
        task_manifest_ref=task_ref,
        tasks=(n.binding,),
        workload=ExecutionWorkload(
            execution_policy_ref=policy_ref,
            task_inputs_ref=inputs_ref,
            seed=params.seed,
        ),
        policies=RunPolicies(
            actor_memory=selected.memory,
            teacher_template=InactivePolicy(
                status="not_applicable",
                reason="Unpaid Actor-only engineering execution",
            ),
        ),
        models=(
            RoleModelPlan(
                role="actor",
                provider="fixed-actor-worker",
                model=(
                    "Qwen/Qwen2.5-7B-Instruct"
                    if context is None
                    else context.profiles[0].model
                ),
                model_binding_ref=actor.spec.model_binding_ref,
                parameters_ref=params_ref,
                paid=False,
            ),
        ),
        resources=RunResources(
            configuration_ref=n.put(actor.spec),
            max_parallel_tasks=1,
            max_actor_generations_per_attempt=20,
            max_interactions_per_attempt=max_interactions,
            operation_timeout_seconds=3600,
            cleanup_timeout_seconds=60,
        ),
        run_capacity=JournalCapacity(
            max_attempts=1, max_entries=32, max_bytes=1024 * 1024, max_entry_bytes=8192
        ),
        budget=None,
    )
    plans = EvidenceRunPlans(actor.evidence, actor.controls)
    run_ref = plans.publish(run, publication_op)
    bound = RunBinding(
        owner=state.owner,
        plan_ref=run_ref,
        release_ref=actor.spec.release_ref,
        submission_key="engineering-source-" + state.owner.job_id,
    )
    assert plans.load(bound, publication_op) == run
    claim = n.raw(
        json.dumps(
            dict(
                engineering_only=True,
                formal_source_admission=False,
                source_binding_ref=n.binding_ref.model_dump(mode="json"),
                baseline_ref=source.saved["baseline_ref"].model_dump(mode="json"),
                site=source.c.spec.token.model_dump(mode="json"),
                browser=browser.spec.token.model_dump(mode="json"),
            )
        ).encode(),
        "engineering-source-claim/1",
    )
    trace = TracePlan(
        binding=AttemptBinding(
            run=bound, task=state.task, attempt_id=state.attempt_id, claim_ref=claim
        ),
        scope=state,
        initial_observation_ref=initial,
        max_generations=20,
        max_interactions=max_interactions,
        capacity=TraceCapacity(
            max_events=128,
            max_bytes=2 * 1024 * 1024,
            max_event_bytes=32768,
            max_trace_bytes=2 * 1024 * 1024,
        ),
    )
    operation = n.request.operation.model_copy(
        update={
            "operation_id": "actual-source-actor",
            "deadline": actor.op.deadline,
            "allocation_id": None,
            "recovery_ref": None,
        }
    )
    request = ActorRunRequest(
        scope=state,
        task=n.public,
        skill=selected.skill,
        memory=selected.memory,
        initial_observation_ref=initial,
        model_allocation=actor.spec.token,
        browser_allocation=browser.spec.token,
        parameters_refs=(params_ref,) * 20,
        operation=operation,
        generation_seconds=120,
        interaction_seconds=30,
        cleanup_seconds=15,
    )
    if context_ref is not None:
        request = ActorRunRequest.model_validate(
            {
                **request.model_dump(),
                "schema_version": "actor-run-request/2",
                "candidate_id": candidate_id,
                "revision_round": 0,
                "context_configuration_ref": context_ref,
            }
        )
    return SourceActorPlan(run, trace, request, choice)
