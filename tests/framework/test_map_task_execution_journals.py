"""Preflight current Map full journals/claim/64K role declarations, no Actor action."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from source_actor_context_fixtures import source_context_case
from actor_long_fixtures import long_config
from map_task_preparation_port_fixtures import preparation_case
from map_task_execution_journal_fixtures import current_map_journals
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
import map_registered_worker_fixtures as registered
from site_worker_fixtures import configuration as original


def test_full_map_frozen_claim_and_pending_candidate_precede_native_task_effects(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = source_context_case(
        node_path / "native64", monkeypatch, engine_config=long_config()
    )

    def configured(*, job_id: str) -> SiteWorkerConfiguration:
        return original(job_id=native.scope.binding.resource.owner.job_id)

    monkeypatch.setattr(registered, "configuration", configured)
    root = node_path / "map"
    root.mkdir()
    try:
        with preparation_case(root, monkeypatch) as p:
            data = current_map_journals(
                p, native, p.original.workspace / "current-task-journals"
            )
            assert p.requests == [] and p.preparation.state.phase == "new"
            snapshot = data.runs.read(p.plan.read_operation)
            assert (
                snapshot.project()[0].stage == "running" and snapshot.project()[1] == ()
            )
            progress = data.construction.read(p.plan.read_operation)
            assert progress.project().pending_attempt == p.plan.intent
            assert data.plans.load(
                p.plan.intent.binding.run, p.plan.read_operation
            ).tasks == (p.source.native.binding,)
            assert (
                data.claims.require(
                    p.plan.intent.binding.claim_ref,
                    p.plan.intent.binding,
                    p.plan.operation,
                ).binding.task
                == p.source.native.binding
            )
            assert native.loader.session.calls == 0
            assert (
                native.params.max_input_tokens == 61440
                and native.params.max_new_tokens == 4096
            )
    finally:
        native.client.close(guard(30))
