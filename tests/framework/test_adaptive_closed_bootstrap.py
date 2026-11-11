"""Owned constructor through original Actor/Reset/closed bootstrap, unit transports."""

from pathlib import Path
from types import SimpleNamespace
import pytest
from lab_generate_skill.actor.context_source import ADAPTIVE_ACTOR_PROTECTION_RULES
from lab_generate_skill.adapters.plans.recorded_observation_sources import (
    RecordedActorObservationSources,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    ObservationTaskBinding,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from actor_engine_fixtures import UnitSession
from actor_context_projection_fixtures import actor_projection_case
from observation_read_fixtures import policy
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


def test_original_owned_actor_and_actual_closed_bootstrap_consume_same_adaptive_source(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import source_actor_context_fixtures as source_fixtures

    selected = ContextProjectionPolicy.model_validate(
        {
            **actor_projection_case().policy.model_dump(),
            "schema_version": "context-projection-policy/2",
            "candidate_order": ("compact_full_ax", "local_ax"),
            "forced_kind": None,
            "protected_rules": ADAPTIVE_ACTOR_PROTECTION_RULES,
            "actor_projection": AdaptiveObservationProjection(
                read_policy=policy(),
                local_bindings=(
                    ObservationTaskBinding(
                        site="map",
                        family="navigation_page_identity",
                        contract_version=1,
                        split="train",
                    ),
                ),
            ),
        }
    )
    monkeypatch.setattr(
        source_fixtures,
        "actor_projection_case",
        lambda: SimpleNamespace(policy=selected),
    )

    def body_tokens(self: UnitSession, text: str) -> tuple[int, ...]:
        return (
            8,
            9,
        )  # Explicit synthetic tokenizer, never actual hardware qualification.

    monkeypatch.setattr(UnitSession, "tokenize_observation", body_tokens, raising=False)
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, owner):
        fixed_task_source_inputs(c, owner, monkeypatch)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success"
        initialized = c.bundle.initialization.original().state.result
        assert initialized is not None
        request = initialized.actor
        store = c.p.original.resource.evidence
        controls = c.p.original.resource.controls
        op = request.operation.cleanup(
            "closed-adaptive-production-review",
            now=c.p.original.resource.clock.utcnow(),
            seconds=120,
        )
        snapshot = c.handles.trace.read(op)
        sent = len(c.native.channel.sent)
        review = closed_actor_context(
            request,
            tuple(c.handles.completed),
            store,
            EvidenceObservations(store, controls),
            control=controls.bind(op),
        )
        assert isinstance(review.observation_sources, RecordedActorObservationSources)
        for ordinal, event in enumerate(snapshot.events):
            if not isinstance(event, GenerationPlanned):
                continue
            prefix = TraceSnapshot(
                plan=snapshot.plan,
                creation_operation=snapshot.creation_operation,
                events=snapshot.events[:ordinal],
            )
            actual = review.verify(
                request, prefix, event.intent, op, control=controls.bind(op)
            )
            assert actual.observation_view is not None
        review.clear_inputs()
        assert len(c.native.channel.sent) == sent
        assert (
            c.bundle.finalization.state.reset is not None
            and c.bundle.finalization.state.reset.status == "safe"
        )
