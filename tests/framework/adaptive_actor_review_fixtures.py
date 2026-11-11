"""Closed original loop/count frames; model/browser transports remain synthetic."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from lab_generate_skill.application.actor_rejection_progress import (
    RecordedActorRejectionProgress,
)
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.plans.recorded_observation_sources import (
    RecordedActorObservationSources,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from adaptive_actor_loop_fixtures import adaptive_loop_case, AdaptiveLoopCase
from test_run_journal import command


@dataclass
class ClosedAdaptiveReview:
    actor: AdaptiveLoopCase
    snapshot: TraceSnapshot
    context: RecordedActorContextInputs
    operation: OperationContext


def closed_adaptive_review(
    root: Path, *, read_policy_changes: dict[str, Any] | None = None
) -> ClosedAdaptiveReview:
    c = adaptive_loop_case(root, read_policy_changes=read_policy_changes)
    snapshot = c.runner.run(c.request)
    client = c.base.base.client
    guard, installed = client.owner_guard, client.installed_sources
    assert guard is not None and installed is not None
    controls = c.base.base.loop.journal.controls
    store = c.base.base.loop.store
    client.close(controls.bind(command("close-read-review-model", attempt="attempt")))
    counts = ActorContextCountReviewer(
        store,
        c.configuration.profiles[0],
        c.base.model_binding,
        c.base.params,
        client.artifact,
        client.config,
        session_id=client.session_id,
        guard=guard,
        installed_sources=installed,
    )
    sources = RecordedActorObservationSources(
        c.configuration, store, rejections=RecordedActorRejectionProgress(store)
    )
    project, protect = build_actor_context(
        c.configuration.policy, indices=sources.index_for_public
    )
    context = RecordedActorContextInputs(
        store,
        EvidenceObservations(store, controls),
        project,
        protect,
        counts,
        observation_sources=sources,
    )
    op = command(
        "closed-complete-adaptive-review",
        attempt="attempt",
        cleanup_parent="original-adaptive-run",
    )
    return ClosedAdaptiveReview(c, snapshot, context, op)
