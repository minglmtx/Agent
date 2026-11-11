"""Original four-candidate method and current Actor2 through one pure task factory."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from construction_multi_task_factory_fixtures import four_current_tasks


def test_four_distinct_current_tasks_share_only_original_run_model_and_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with four_current_tasks(tmp_path / "case", monkeypatch) as case:
        assert len(case.calls) == len(case.tasks) == len(case.port.tasks) == 4
        assert len({c.task.plan.intent.binding.attempt_id for c in case.tasks}) == 4
        assert len({id(c.task.browser) for c in case.tasks}) == 4
        assert len({id(c.task.phases) for c in case.tasks}) == 4
        assert len({id(c.resources.journal) for c in case.tasks}) == 4
        assert len({id(c.task.deps.runs) for c in case.tasks}) == 1
        assert case.native.loader.session.calls == 4
        for current in case.tasks:
            c = current.task
            assert current.source.task is c
            assert (
                c.phases.calls.count("acquire") == c.phases.calls.count("restore") == 1
            )
            assert len(current.completed) == 1
            assert current.native is case.native
            with pytest.raises(DispatchAlreadyCommitted):
                case.port.execute(c.plan.intent, c.plan.operation)
        first = case.tasks[0].task
        progress = case.port.construction.journal.read(first.plan.read_operation)
        assert len(progress.project().attempts) == 4
        assert progress.project().next_action.kind == "revise"
        assert all(
            a.evaluation.status == "failure" for a in progress.project().attempts
        )
        assert all(
            a.stage == "sealed"
            for a in first.deps.runs.read(first.plan.read_operation).project()[1]
        )
        assert case.native.loader.session.calls == 4
