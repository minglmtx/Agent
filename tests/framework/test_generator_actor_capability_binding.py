"""Selected public capability through actual prepare/register/native send gates."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.construction_preparation import (
    prepare_generator_step,
)
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.domain.construction_control import GenerateConstructionWork
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.actor_projection import (
    FullAxProjection,
    AdaptiveObservationProjection,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.generator.prompting import prepare_generator
from lab_generate_skill.policies.construction_actor_capabilities import (
    construction_actor_capabilities,
    check_construction_actor_request,
)
from lab_generate_skill.bootstrap.construction_actor_configuration import (
    verify_selected_construction_factory,
)
from generator_actor_capability_fixtures import (
    selected_configuration,
    selected_preparation_case,
)
from test_construction_inputs import generation_input
from test_construction_state import initial


@pytest.mark.parametrize("local", [False, True])
def test_selected_configuration_actual_preparation_and_first_native_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local: bool
) -> None:
    c = selected_preparation_case(tmp_path / "case", monkeypatch, local=local)
    request = c.request()
    before = c.control.journal.read(request.operation)
    saved = prepare_generator_step(request, c.deps)
    c.native.assert_no_inference()
    assert isinstance(saved.step.work, GenerateConstructionWork)
    public = saved.step.work.request
    assert (
        isinstance(public, GenerationInput)
        and public.schema_version == "generation-input/2"
    )
    capabilities = public.actor_capabilities
    assert capabilities is not None
    assert bool(capabilities.conditional_read_tools) is local
    assert len(public.retrieved_skills) == 6
    for private in (
        "actor_context_configuration_ref",
        "claim_ref",
        "StateScope",
        "routing_ref",
        "configuration_ref",
    ):
        assert private not in public.model_dump_json()
    observation = EvidenceObservations(c.native.data.store, c.native.controls).load(
        public.context.initial_observation_ref, request.operation
    )
    prompt = prepare_generator(public, observation)
    assert prompt.prompt_version == "webarena-generator-v7-selected-actor"
    data = json.loads(prompt.messages[1].content)
    assert data["actor_capabilities"]["conditional_read_tools"] == list(
        capabilities.conditional_read_tools
    )
    assert data["actor_capabilities"]["registered_read_tools"] == []
    assert (
        "No partition-read tool is currently registered."
        not in prompt.messages[0].content
    )
    assert "initial" in prompt.messages[0].content.lower()
    assert c.control.journal.read(request.operation) == before
    result = construct_targets(saved.step, c.control)
    assert result.status == "advanced" and c.native.engine.calls == 1
    assert len(result.progress.project().candidates) == 1
    assert result.progress.project().next_action.candidate_slot == 1


@pytest.mark.parametrize("new", [False, True])
def test_legacy_canonical_wire_and_explicit_null_rejection(new: bool) -> None:
    if new:
        value = generation_input()
        assert "actor_capabilities" not in value.model_dump_json()
        data = value.model_dump(mode="python")
        data["actor_capabilities"] = None
        with pytest.raises(ValidationError):
            GenerationInput.model_validate(data)
    else:
        old_plan = initial().plan
        assert "actor_context_configuration_ref" not in old_plan.model_dump_json()
        data = old_plan.model_dump(mode="python")
        data["actor_context_configuration_ref"] = None
        with pytest.raises(ValidationError):
            ConstructionPlan.model_validate(data)


def test_actual_context_model_role_and_local_binding_are_not_global_flags() -> None:
    plan = initial().plan
    configuration = selected_configuration(plan)
    capabilities = construction_actor_capabilities(plan, configuration)
    assert capabilities.read_limits is not None
    assert capabilities.read_limits.reads_per_observation == 6
    projection = configuration.policy.actor_projection
    assert isinstance(projection, AdaptiveObservationProjection)
    unsupported = projection.model_copy(
        update={
            "local_bindings": tuple(
                b.model_copy(update={"family": "other-family"})
                for b in projection.local_bindings
            )
        }
    )
    changed = configuration.model_copy(
        update={
            "policy": configuration.policy.model_copy(
                update={"actor_projection": unsupported}
            )
        }
    )
    assert construction_actor_capabilities(plan, changed).conditional_read_tools == ()
    wrong = ActorContextConfiguration.model_validate(
        configuration.model_copy(
            update={
                "profiles": tuple(
                    p.model_copy(update={"model": "another-actor"})
                    for p in configuration.profiles
                )
            }
        )
    )
    with pytest.raises(OwnershipConflict, match="model role"):
        construction_actor_capabilities(plan, wrong)


def test_new_plan_rejects_a_flag_factory_before_any_task_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = selected_preparation_case(tmp_path / "case", monkeypatch)
    request = c.request()
    plan = c.control.journal.read(request.operation).plan
    from unittest.mock import Mock
    from lab_generate_skill.ports.task_execution import TaskActorBinding
    from lab_generate_skill.domain.task_execution import TaskExecutionPlan

    actor = Mock(spec=TaskActorBinding)
    task = Mock(spec=TaskExecutionPlan)
    with pytest.raises(OwnershipConflict, match="actual original"):
        verify_selected_construction_factory(
            plan,
            task,
            actor,
            c.native.data.store,
            c.control.controls.bind(request.operation),
        )
    actor.bind.assert_not_called()
    c.native.assert_no_inference()


def test_selected_actual_actor_gate_precedes_native_request_and_retains_reads(
    tmp_path: Path,
) -> None:
    from adaptive_actor_loop_fixtures import adaptive_loop_case
    from lab_generate_skill.application.construction_actor_configuration import (
        verify_construction_actor_configuration,
    )

    c = adaptive_loop_case(tmp_path)
    request = c.request
    store = c.base.base.loop.store
    control = c.runner.deps.controls.bind(request.operation)
    assert request.context_configuration_ref is not None
    configuration = ActorContextConfiguration.model_validate_json(
        store.read(request.context_configuration_ref)
    )
    old = initial().plan
    actor_profile = configuration.profiles[0]
    models = tuple(
        (
            m.model_copy(
                update={
                    "model": actor_profile.model,
                    "model_binding_ref": actor_profile.routing_ref,
                }
            )
            if m.role == "actor"
            else m
        )
        for m in old.models
    )
    plan = ConstructionPlan.model_validate(
        old.model_copy(
            update={
                "schema_version": "construction-plan/4",
                "actor_context_configuration_ref": request.context_configuration_ref,
                "task": old.task.model_copy(update={"identity": request.task.identity}),
                "models": models,
            }
        )
    )
    wrong = plan.model_copy(
        update={"actor_context_configuration_ref": old.run.plan_ref}
    )
    with pytest.raises(OwnershipConflict, match="changed the configuration"):
        verify_construction_actor_configuration(wrong, request, store, control)
    assert c.session.calls == 0 and not c.executions
    verify_construction_actor_configuration(plan, request, store, control)
    assert c.session.calls == 0
    result = c.runner.run(request).project().sealed
    assert result is not None and result.generations == 2 and result.interactions == 1
    assert c.session.calls == 2 and len(c.executions) == 2
    assert result.turns[0].reading is not None and result.turns[0].interaction is None
