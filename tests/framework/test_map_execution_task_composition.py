"""Single Actor default Map/lifecycle/closed review; services/permissions synthetic.

The complete42 plan and semantics remain authoritative. Five structural branches
exercise software composition; they are not 42 actual runs or source permission.
"""

from pathlib import Path
import traceback
import pytest
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    TaskCaptureResult,
    ClosedTaskResources,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from lab_generate_skill.adapters.sites.task_site_capture_authority import (
    OriginalTaskSiteCaptureAuthority,
)
from map_execution_task_fixtures import single_map_execution_case
from map_navigation_evaluation_fixtures import closed_review
from map_task_execution_review_fixtures import map_task_review_facts
from site_instance_fixtures import node_path as node_path

# One software representative for each of the already selected group's initial
# branches. Every member retains its separate actual admission/result row.
BRANCHES = (
    "125732d3658ab4daee02",  # plain_map
    "0e969f70c08ad9d881ef",  # search
    "20a1eabbba54974e8549",  # directions
    "2839e82dcf1d04ce3405",  # traces
    "71099c255a288120463c",  # communities
)


@pytest.mark.parametrize("source_id", BRANCHES)
def test_single_default_map_uses_same_complete_lifecycle_and_independent_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with single_map_execution_case(node_path, monkeypatch, source_id) as c:
        p, bundle = c.p, c.bundle
        assert not hasattr(bundle.task.deps, "construction")
        run = c.journals.plans.load(p.plan.intent.binding.run, p.plan.read_operation)
        assert isinstance(run.workload, ExecutionWorkload)
        assert tuple(r.role for r in run.models) == ("actor",)
        try:
            result = bundle.task.execute(p.plan.intent, p.plan.operation)
        except TaskExecutionUnconfirmed as error:
            if error.primary is not None:
                traceback.print_exception(error.primary)
            for failure in error.cleanup_errors:
                traceback.print_exception(failure)
            raise
        assert isinstance(result, ExecutionTaskResult)
        assert result.evaluation.status == "success"
        assert (
            result.generations
            == result.interactions
            == c.native.loader.session.calls
            == 1
        )
        assert c.authority.initial_calls == 1 and c.actor.calls > 1
        assert bundle.preparation.state.result is not None
        assert bundle.initialization.original().state.result is not None
        assert isinstance(
            bundle.capture.site_authority, OriginalTaskSiteCaptureAuthority
        )
        assert bundle.capture.site_authority.consumed
        assert bundle.finalization.state.reset is not None
        assert bundle.finalization.state.reset.status == "safe"
        attempt = c.journals.runs.read(p.plan.read_operation).project()[1][0]
        assert attempt.stage == "sealed"
        assert [e.stage for e in attempt.events] == [
            "planned",
            "acquiring",
            "preparing",
            "starting",
            "baseline_verified",
            "executing",
            "captured",
            "evaluated",
            "closing",
            "restoring",
            "sealed",
        ]
        refs = [r for e in attempt.events for r in e.outputs]
        assert any(r.content_schema == "prepared-actor-input/2" for r in refs)
        assert not any(
            r.content_schema
            in (
                "construction-plan/1",
                "generator-result/1",
                "teacher-result/1",
                "prepared-actor-input/1",
            )
            for r in refs
        )
        facts = map_task_review_facts(p, bundle, c.handles, result)
        with pytest.raises(DispatchAlreadyCommitted):
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert c.native.loader.session.calls == 1
        original = p.original
    closed_review(original, facts)


def test_single_default_valid_failure_still_reviews_and_restores(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with single_map_execution_case(
        node_path, monkeypatch, BRANCHES[0], negative=True
    ) as c:
        p = c.p
        result = c.bundle.task.execute(p.plan.intent, p.plan.operation)
        assert result.evaluation.status == "failure" and result.evaluation.reward == 0
        facts = map_task_review_facts(p, c.bundle, c.handles, result)
        original = p.original
    closed_review(original, facts)


def test_single_default_revoked_original_claim_refuses_before_fresh_worker(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with single_map_execution_case(node_path, monkeypatch, BRANCHES[0]) as c:
        c.journals.claim_authority.denied = True
        with pytest.raises(OwnershipConflict):
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert not c.p.requests and c.handles.browser is None
        assert c.p.original.worker is None and c.native.loader.session.calls == 0


@pytest.mark.parametrize(
    "fault",
    [
        "capture",
        "capture-and-cleanup",
        "cancel-after-unique0",
        "initializer-partial",
        "actor-revoked",
    ],
)
def test_single_default_preserves_primary_cleanup_unknown_and_once_identity(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with single_map_execution_case(node_path, monkeypatch, BRANCHES[0]) as c:
        p, bundle = c.p, c.bundle
        primary = TimeoutError("Original synthetic terminal capture unknown")
        cleanup = OSError("Original synthetic restore failed")
        if fault.startswith("capture"):

            def lost(
                plan: TaskExecutionPlan,
                snapshot: TraceSnapshot,
                operation: OperationContext,
                control: OperationControl,
            ) -> TaskCaptureResult:
                assert plan == p.plan and snapshot.plan.binding == plan.intent.binding
                control.checkpoint()
                raise primary

            monkeypatch.setattr(bundle.capture, "capture", lost)
            if fault == "capture-and-cleanup":

                def failed_restore(
                    plan: TaskExecutionPlan,
                    closed: ClosedTaskResources,
                    operation: OperationContext,
                    control: OperationControl,
                ) -> EvidenceRef:
                    assert operation.mode == "cleanup" and closed.reset_plan == p.reset
                    control.checkpoint()
                    raise cleanup

                monkeypatch.setattr(bundle.finalization, "restore", failed_restore)
        elif fault == "actor-revoked":
            c.actor.denied = True
        else:
            original_factory = bundle.initialization.factory

            def factory(
                plan: TaskExecutionPlan,
                operation: OperationContext,
                control: OperationControl,
            ) -> RecordedTaskInitialization:
                producer = original_factory(plan, operation, control)
                if fault == "initializer-partial":
                    assert (
                        c.handles.browser is not None
                        and c.handles.browser.phase == "new"
                    )
                    raise primary
                original_start = producer.start

                def cancelled(
                    plan: TaskExecutionPlan,
                    operation: OperationContext,
                    control: OperationControl,
                ) -> InitializedTask:
                    original_start(plan, operation, control)
                    raise OperationStopped("CANCELLED", operation.operation_id)

                monkeypatch.setattr(producer, "start", cancelled)
                return producer

            monkeypatch.setattr(bundle.initialization, "factory", factory)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            bundle.task.execute(p.plan.intent, p.plan.operation)
        error = caught.value
        assert error.primary is not None and error.evaluation is None
        assert bundle.capture.state.selection_ref is None
        if fault.startswith("capture") or fault == "initializer-partial":
            assert error.primary is primary
        if fault == "capture-and-cleanup":
            assert error.cleanup_errors == (cleanup,)
            assert (
                bundle.finalization.state.reset is None and "reset" not in error.known
            )
            assert [r.action for r in p.requests] == ["snapshot", "prepare"]
        else:
            assert error.cleanup_errors == () and "reset" in error.known
            assert bundle.finalization.state.reset is not None
            assert bundle.finalization.state.reset.status == "safe"
            assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
        assert c.native.loader.session.calls == (
            1 if fault.startswith("capture") else 0
        )
        attempt = c.journals.runs.read(p.plan.read_operation).project()[1][0]
        assert attempt.stage == "sealed" and attempt.stop_reason is not None
        if fault == "cancel-after-unique0":
            assert (
                isinstance(error.primary, OperationStopped)
                and attempt.stop_reason == "cancelled"
            )
        if fault == "actor-revoked":
            assert isinstance(error.primary, OwnershipConflict)
        before = c.native.loader.session.calls
        with pytest.raises(DispatchAlreadyCommitted):
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert c.native.loader.session.calls == before
