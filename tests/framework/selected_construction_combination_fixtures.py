"""Declare selected fixture configuration before original journal/task creation.

No original record is rewritten. Existing unit model/source/Teacher authorities
remain unit facts; this fixture cannot grant a physical or formal training run.
"""

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.actor_context_runtime import freeze_actor_context
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    FullAxProjection,
    ObservationTaskBinding,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    ConstructionCall,
    CallPlanned,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.policies.construction_actor_capabilities import (
    construction_actor_capabilities,
)
from lab_generate_skill.actor.context_source import ADAPTIVE_ACTOR_PROTECTION_RULES
from observation_read_fixtures import policy as read_policy
from source_actor_context_fixtures import source_context_case
import construction_storage_fixtures as storage
import task_actor_v2_fixtures as actor
import task_teacher_source_fixtures as teacher
import construction_multi_task_factory_fixtures as factory
from test_slurm_commands import guard


@contextmanager
def selected_construction_environment(
    patch: pytest.MonkeyPatch, *, local: bool
) -> Iterator[None]:
    active: list[Any] = []
    original_fixture, original_event = storage.fixture, storage.StorageFixture.event

    def native(path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Any:
        value = source_context_case(path, monkeypatch, **kwargs)
        task = value.source.native.public.identity
        binding = ObservationTaskBinding(
            site=task.site,
            family=task.family,
            contract_version=task.contract_version,
            split=task.split,
        )
        projection = (
            AdaptiveObservationProjection(
                read_policy=read_policy(), local_bindings=(binding,)
            )
            if local
            else FullAxProjection()
        )
        value.policy = ContextProjectionPolicy.model_validate(
            value.policy.model_copy(
                update={
                    "schema_version": (
                        "context-projection-policy/2"
                        if local
                        else "context-projection-policy/1"
                    ),
                    "candidate_order": (
                        ("compact_full_ax", "local_ax") if local else ("identity",)
                    ),
                    "actor_projection": projection,
                    "protected_rules": (
                        ADAPTIVE_ACTOR_PROTECTION_RULES
                        if local
                        else value.policy.protected_rules
                    ),
                }
            )
        )
        active.append(value)
        return value

    def fixture(
        path: Path,
        *,
        recorded_teacher: bool = False,
        site: Site = "map",
        allowed_actions: tuple[str, ...] = ("stop",),
    ) -> storage.StorageFixture:
        data = original_fixture(
            path,
            recorded_teacher=recorded_teacher,
            site=site,
            allowed_actions=allowed_actions,
        )
        value = active[-1]
        role = next(m for m in data.plan.models if m.role == "actor")
        configuration = freeze_actor_context(
            value.scope.spec,
            (role.parameters_ref,) * data.plan.max_actor_generations,
            value.policy,
            data.store,
            soft_target=24576,
            control=guard(30),
        )
        reference = storage.put(
            data.store, configuration, "actor-context-configuration/1"
        )
        data.plan = ConstructionPlan.model_validate(
            data.plan.model_copy(
                update={
                    "schema_version": "construction-plan/4",
                    "actor_context_configuration_ref": reference,
                }
            )
        )
        return data

    def event(
        self: storage.StorageFixture, progress: ConstructionProgress, **kwargs: Any
    ) -> ProgressEvent:
        result = original_event(self, progress, **kwargs)
        if isinstance(result, CallPlanned) and result.call.role == "generator":
            # Synthetic provider input is declared before first journal append.
            # Actual Generator prepare/send is independently covered by119 cases.
            old = GenerationInput.model_validate_json(
                self.store.read(result.call.input_ref)
            )
            reference = self.plan.actor_context_configuration_ref
            assert reference is not None
            configuration = ActorContextConfiguration.model_validate_json(
                self.store.read(reference)
            )
            selected = GenerationInput.model_validate(
                old.model_copy(
                    update={
                        "schema_version": "generation-input/2",
                        "actor_capabilities": construction_actor_capabilities(
                            self.plan, configuration
                        ),
                    }
                )
            )
            saved = storage.put(self.store, selected, "generation-input/2", "public")
            call = ConstructionCall.model_validate(
                result.call.model_copy(
                    update={"schema_version": "construction-call/2", "input_ref": saved}
                )
            )
            return CallPlanned(operation=result.operation, call=call)
        return result

    with patch.context() as declarations:
        for module in (actor, teacher, factory):
            declarations.setattr(module, "source_context_case", native)
        declarations.setattr(storage, "fixture", fixture)
        declarations.setattr(storage.StorageFixture, "event", event)
        yield
