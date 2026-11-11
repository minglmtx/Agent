"""Current Actor2/context declarations, with explicit synthetic model/claim rights."""

from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from map_actor_trace_fixtures import BrowserActorCase
from browser_resource_fixtures import ResourceCase
from evidence_control_fixtures import EvidenceFixtureStore
from actor_context_projection_fixtures import actor_projection_case
from context_budget_fixtures import profile
from test_evidence_run_plans import persisted_plan, frozen_binding
from test_actor_protocol import turn
from state_contract_fixtures import allocation, recovery
from preparation_record_fixtures import put
from retrieval_fixtures import reference


def current_actor(
    case: BrowserActorCase,
    browser: ResourceCase,
    session: EvidenceBrowserSession,
    store: EvidenceFixtureStore,
) -> tuple[ActorRunRequest, AttemptBinding]:
    old = persisted_plan(store)
    run = RunPlan.model_validate(
        old.model_copy(
            update={
                "tasks": (
                    old.tasks[0].model_copy(update={"identity": case.scope.task}),
                ),
                "resources": old.resources.model_copy(
                    update={
                        "max_actor_generations_per_attempt": 1,
                        "max_interactions_per_attempt": 1,
                    }
                ),
            }
        )
    )
    bound = frozen_binding(store, run).model_copy(update={"owner": case.scope.owner})
    binding = AttemptBinding(
        run=bound,
        task=case.scope.task,
        attempt_id=case.scope.attempt_id,
        claim_ref=reference(
            {"explicit_synthetic_actor2_claim": True}, "source-claim/1", store=store
        ),
    )
    params = LocalActorParameters(
        max_input_tokens=61440, max_new_tokens=4096, seed=0, temperature=0.0, top_p=1.0
    )
    parameters = reference(params, "model-parameters/1", store=store)
    context = ActorContextConfiguration(
        policy=actor_projection_case(site="shopping_admin").policy,
        profiles=(
            profile(
                provider="fixed-actor-worker",
                configuration_ref=parameters,
                context_window=65536,
                output_reserve=4096,
                input_limit=61440,
                soft_target=24576,
            ),
        ),
    )
    saved = recovery(False).model_copy(update={"owner": case.scope.owner})
    model = allocation("actor", attempt=False).model_copy(
        update={
            "owner": case.scope.owner,
            "recovery_ref": put(store, saved),
        }
    )
    public = turn()
    assert session.observation_ref is not None
    return (
        ActorRunRequest(
            schema_version="actor-run-request/2",
            candidate_id="navigation-candidate",
            revision_round=0,
            context_configuration_ref=put(store, context),
            scope=case.scope,
            task=browser.spec.configuration.spec.task,
            skill=public.skill,
            memory=public.memory,
            initial_observation_ref=session.observation_ref,
            model_allocation=model,
            browser_allocation=browser.spec.token,
            parameters_refs=(parameters,),
            operation=browser.op.model_copy(
                update={
                    "operation_id": "admin-current-actor",
                    "allocation_id": None,
                    "recovery_ref": None,
                }
            ),
            generation_seconds=30,
            interaction_seconds=30,
            cleanup_seconds=30,
        ),
        binding,
    )
