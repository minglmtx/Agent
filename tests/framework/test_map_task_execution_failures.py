"""Current default valid failure/unknown/cancel/partial; no original source replay."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_group_cases import SOURCES
from map_navigation_evaluation_fixtures import closed_review
from map_task_execution_current_fixtures import current_map_execution_case
from map_task_execution_review_fixtures import current_map_review_facts
from site_instance_fixtures import node_path as node_path


def test_default_business_negative_keeps_original_failure_and_complete_closed_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_map_execution_case(
        node_path, monkeypatch, SOURCES[0], negative=True
    ) as case:
        result = case.bundle.task.execute(case.p.plan.intent, case.p.plan.operation)
        assert result.evaluation.status == "failure" and result.evaluation.reward == 0
        facts = current_map_review_facts(case, result)
        assert facts["expected_status"] == "failure"
        original = case.p.original
    closed_review(original, facts)


@pytest.mark.parametrize(
    "fault", ["model-return-lost", "initializer-factory-lost", "cancel-after-unique0"]
)
def test_current_default_preserves_unknown_or_cancel_after_owned_cleanup_no_replay(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as case:
        p, bundle = case.p, case.bundle
        original_factory = bundle.initialization.factory
        if fault == "model-return-lost":
            original_generate = case.native.client.generate_exchange
            injected: list[bool] = []

            def lost(*args: Any, **kwargs: Any) -> Any:
                original_generate(*args, **kwargs)
                injected.append(True)
                raise TimeoutError("Synthetic original native generation return lost")

            monkeypatch.setattr(case.native.client, "generate_exchange", lost)
        else:

            def factory(
                plan: TaskExecutionPlan,
                operation: OperationContext,
                control: OperationControl,
            ) -> RecordedTaskInitialization:
                producer = original_factory(plan, operation, control)
                if fault == "initializer-factory-lost":
                    raise TimeoutError(
                        "Synthetic initializer factory ack lost after owner retention"
                    )
                original_start = producer.start

                def cancel(
                    plan: TaskExecutionPlan,
                    operation: OperationContext,
                    control: OperationControl,
                ) -> InitializedTask:
                    original_start(plan, operation, control)
                    raise OperationStopped("CANCELLED", operation.operation_id)

                monkeypatch.setattr(producer, "start", cancel)
                return producer

            monkeypatch.setattr(bundle.initialization, "factory", factory)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            bundle.task.execute(p.plan.intent, p.plan.operation)
        error = caught.value
        assert error.primary is not None and error.evaluation is None
        if fault == "model-return-lost":
            assert injected == [True]
        assert error.cleanup_errors == () and "reset" in error.known
        assert bundle.finalization.state.reset is not None
        assert bundle.finalization.state.reset.status == "safe"
        assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
        assert bundle.capture.state.selection_ref is None
        assert case.native.loader.session.calls == (
            1 if fault == "model-return-lost" else 0
        )
        assert (
            case.handles.backend is not None
            and case.handles.backend.calls.count("actual_action") == 0
        )
        attempt = case.journals.runs.read(p.plan.read_operation).project()[1][0]
        assert attempt.stage == "sealed" and attempt.stop_reason is not None
        if fault == "cancel-after-unique0":
            assert attempt.stop_reason == "cancelled" and isinstance(
                error.primary, OperationStopped
            )
        before = case.native.loader.session.calls
        with pytest.raises(DispatchAlreadyCommitted):
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert case.native.loader.session.calls == before
