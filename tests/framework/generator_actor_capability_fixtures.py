"""Original CAS/journal fixtures; all model/native authorities remain synthetic."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    FullAxProjection,
    ObservationTaskBinding,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.evidence import EvidenceMetadata
from context_budget_fixtures import profile
import construction_storage_fixtures as storage
from construction_preparation_fixtures import preparation_case, PreparationCase
from observation_read_fixtures import policy as read_policy


def selected_configuration(
    plan: ConstructionPlan, *, local: bool = True
) -> ActorContextConfiguration:
    actor = next(m for m in plan.models if m.role == "actor")
    binding = ObservationTaskBinding(
        site=plan.task.identity.site,
        family=plan.task.identity.family,
        contract_version=plan.task.identity.contract_version,
        split=plan.task.identity.split,
    )
    projection = (
        AdaptiveObservationProjection(
            read_policy=read_policy(), local_bindings=(binding,)
        )
        if local
        else FullAxProjection()
    )
    return ActorContextConfiguration(
        policy=ContextProjectionPolicy(
            schema_version=(
                "context-projection-policy/2"
                if local
                else "context-projection-policy/1"
            ),
            role="actor",
            policy_id="unit-selected-policy",
            implementation_sha256="f" * 64,
            software_evidence_ref=plan.run.plan_ref,
            protected_rules=("original-object-and-context",),
            candidate_order=("compact_full_ax", "local_ax") if local else ("identity",),
            allow_identity_fallback=True,
            forced_kind=None,
            actor_projection=projection,
        ),
        profiles=(
            profile(
                model=actor.model,
                provider="fixed-actor-worker",
                routing_ref=actor.model_binding_ref,
                configuration_ref=actor.parameters_ref,
                context_window=65536,
                output_reserve=4096,
                input_limit=61440,
                soft_target=24576,
            ),
        ),
    )


def selected_preparation_case(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, local: bool = True
) -> PreparationCase:
    original = storage.fixture

    def make(
        path: Path,
        *,
        recorded_teacher: bool = False,
        site: str = "map",
        allowed_actions: tuple[str, ...] = ("stop",),
    ) -> storage.StorageFixture:
        # Preserve the original fixture's actual argument semantics/types.
        from lab_generate_skill.domain.identity import Site
        from typing import cast

        data = original(
            path,
            recorded_teacher=recorded_teacher,
            site=cast(Site, site),
            allowed_actions=allowed_actions,
        )
        configuration = selected_configuration(data.plan, local=local)
        ref = data.store.put(
            configuration.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="actor-context-configuration/1",
                visibility="private",
                producer="unit-selected-generator-actor",
            ),
        )
        data.plan = ConstructionPlan.model_validate(
            data.plan.model_copy(
                update={
                    "schema_version": "construction-plan/4",
                    "actor_context_configuration_ref": ref,
                }
            )
        )
        return data

    with monkeypatch.context() as patch:
        patch.setattr(storage, "fixture", make)
        return preparation_case(root)
