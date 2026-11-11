"""Current task entry -> shared v2 full count/send/once -> closed native review."""

from pathlib import Path
import pytest
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.context_projection import ActorContextSource
from source_review_records import ReadOnlyEvidence
from source_actor_review import review_actor
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.identity import Site
from task_actor_v2_fixtures import current_task_case
from test_run_journal import command


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_current_task_uses_shared_v2_complete_budget_native_frames_and_closed_readonly_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, site: Site
) -> None:
    c = current_task_case(tmp_path / "case", monkeypatch, site=site)
    task = c.task
    result = execute_task(task.plan, task.deps)
    request = task.phases.initialized.actor
    snapshot = TraceSnapshot.model_validate(
        c.resources.journal.read(command(attempt=request.scope.attempt_id))
    )
    generation = next(
        event.intent
        for event in snapshot.events
        if isinstance(event, GenerationPlanned)
    )
    assert (
        request.schema_version == "actor-run-request/2"
        and generation.schema_version == "actor-generation-intent/2"
    )
    assert generation.context_preparation_ref is not None
    assert (
        result.generations
        == result.interactions
        == len(c.completed)
        == c.native.loader.session.calls
        == task.browser.calls
        == 1
    )
    assert result.evaluation.status == "failure"
    assert request.task.identity.site == site
    preparation = ContextPreparationReceipt.model_validate_json(
        task.admission.data.store.read(generation.context_preparation_ref)
    )
    assert (
        preparation.decision is not None
        and preparation.decision.selected_input_ref == generation.input_ref
    )
    assert isinstance(preparation.request.source, ActorContextSource)
    assert preparation.request.source.candidate_id == request.candidate_id
    assert c.completed[0].call.intent == generation
    close = command("current-task-model-closed", attempt=request.scope.attempt_id)
    c.native.client.close(task.deps.controls.bind(close))
    sent = len(c.native.channel.sent)
    readonly = ReadOnlyEvidence(tmp_path / "case/original-task/evidence")
    context = closed_actor_context(
        request,
        tuple(c.completed),
        readonly,
        EvidenceObservations(readonly, task.deps.controls),
        control=task.deps.controls.bind(close),
    )
    summary = review_actor(
        request,
        snapshot,
        tuple(c.completed),
        readonly,
        task.deps.controls,
        close,
        project=build_actor_projection(FullAxProjection()),
        context=context,
    )
    assert summary["generations"] == 1 and len(c.native.channel.sent) == sent
