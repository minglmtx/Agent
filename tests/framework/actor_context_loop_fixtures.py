"""Original loop/once ledger/native service plus synthetic model/browser/source rights."""

from dataclasses import dataclass, replace
from pathlib import Path
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
from lab_generate_skill.application.actor_context_preparation import (
    ControlledActorContext,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.adapters.models.context_tokens import (
    ActorContextTokenCounter,
    actor_budget_profile,
)
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_context_projection_fixtures import actor_projection_case
from local_actor_fixtures import case as local_case, Case
from retrieval_fixtures import reference


class RecordedUnitBrowser:
    def __init__(self, c: Case) -> None:
        self.case = c

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult:
        c = self.case
        result = c.loop.browser.step(action, operation, control=control)
        observed = Observation.model_validate_json(
            c.loop.store.read(result.observation_ref, control)
        )
        raw = BrowserReadout(
            scope=c.loop.request.scope,
            operation=operation,
            action=action,
            observation=observed,
            events=(),
            environment_reward=0.0,
            terminated=False,
            truncated=False,
            protocol_terminal=result.terminal,
        )
        return StepResult.model_validate(
            result.model_copy(
                update={
                    "return_ref": reference(
                        raw, "browser-step-return/1", store=c.loop.store
                    )
                }
            )
        )


@dataclass
class ContextLoopCase:
    base: Case
    request: ActorRunRequest
    config: ActorContextConfiguration
    model_binding: ActorModelBinding
    params: LocalActorParameters
    context: ControlledActorContext
    input_review: RecordedActorContextInputs
    authority: TraceActorAuthority
    runner: RecordedActorRunner
    model: RecordedLocalActorModel
    executions: list[LocalActorExecution]


def context_loop_case(root: Path, *, input_limit: int = 100) -> ContextLoopCase:
    c = local_case(root)
    params = LocalActorParameters.model_validate_json(
        c.loop.store.read(c.intent.parameters_ref)
    )
    if input_limit != params.max_input_tokens:
        params = LocalActorParameters.model_validate(
            {**params.model_dump(), "max_input_tokens": input_limit}
        )
    params_ref = reference(params, "model-parameters/1", store=c.loop.store)
    model_binding = ActorModelBinding(
        model="unit/qwen2",
        release_ref=c.binding.release_ref,
        component_id="actor",
        model_artifact_id=c.client.artifact.artifact_id,
        engine_config_artifact_id="actor-config",
        engine_config_ref=reference(
            c.client.config, "actor-engine-config/1", store=c.loop.store
        ),
    )
    model_ref = reference(model_binding, "model-binding/1", store=c.loop.store)
    binding = c.binding.model_copy(update={"model_binding_ref": model_ref})
    policy = actor_projection_case().policy
    profile = actor_budget_profile(
        c.client.artifact,
        c.client.config,
        model_binding,
        model_ref,
        params,
        params_ref,
        soft_target=min(80, input_limit),
    )
    config = ActorContextConfiguration(
        policy=policy, profiles=(profile,) * len(c.loop.request.parameters_refs)
    )
    request = ActorRunRequest.model_validate(
        {
            **c.loop.request.model_dump(),
            "schema_version": "actor-run-request/2",
            "candidate_id": "original-unit-candidate",
            "revision_round": 0,
            "context_configuration_ref": reference(
                config, "actor-context-configuration/1", store=c.loop.store
            ),
            "model_allocation": binding.resource,
            "parameters_refs": (params_ref,) * len(c.loop.request.parameters_refs),
            "generation_seconds": 30,
        }
    )
    project, protect = build_actor_context(policy)
    counter = ActorContextTokenCounter(
        c.client,
        c.loop.store,
        profile,
        model_binding,
        params,
        session_id=c.client.session_id,
    )
    guard, sources = c.client.owner_guard, c.client.installed_sources
    assert guard is not None and sources is not None
    count_review = ActorContextCountReviewer(
        c.loop.store,
        profile,
        model_binding,
        params,
        c.client.artifact,
        c.client.config,
        session_id=c.client.session_id,
        guard=guard,
        installed_sources=sources,
    )
    inputs = RecordedActorContextInputs(
        c.loop.store, c.loop.runner.deps.observations, project, protect, count_review
    )
    context = ControlledActorContext(
        request,
        c.loop.journal,
        c.loop.store,
        c.loop.runner.deps.observations,
        c.loop.authority,
        c.loop.journal.controls,
        project,
        protect,
        counter,
    )
    completed: list[LocalActorExecution] = []

    class Returns(TraceActorAuthority):
        def verify_return(
            self, execution: LocalActorExecution, control: OperationControl
        ) -> None:
            super().verify_return(execution, control)
            completed.append(execution)

    authority = Returns(
        request,
        c.loop.journal,
        c.loop.store,
        c.loop.runner.deps.observations,
        c.loop.runner.deps.project,
        c.loop.authority,
        c.loop.journal.controls,
        context=inputs,
    )
    model = RecordedLocalActorModel(
        c.root, binding, c.client, c.loop.store, c.loop.journal.controls, authority
    )
    runner = RecordedActorRunner(
        replace(
            c.loop.runner.deps,
            context=context,
            model=model,
            browser=RecordedUnitBrowser(c),
        )
    )
    return ContextLoopCase(
        c,
        request,
        config,
        model_binding,
        params,
        context,
        inputs,
        authority,
        runner,
        model,
        completed,
    )
