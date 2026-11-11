"""Current Group initial/native/trace/closure/judgment; explicit unit premises."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_source import GROUP_NATIVE_PINS
from lab_generate_skill.bootstrap.gitlab_group_task_capture import (
    RecordedGroupEvaluator,
)
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.bootstrap.gitlab_group_task_finalization import (
    gitlab_group_task_finalization,
)
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from preparation_record_fixtures import put
from test_gitlab_group_task_ports import UnitCleanupRights, close_and_restore
from lab_generate_skill.sites.gitlab.group_terminal_schema import GroupCapturedSelection
from gitlab_group_current_capture_fixtures import current_group_case
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("source", GROUP_NATIVE_PINS)
def test_all_group_current_initial_native_actor_terminal_closed_guard_original_judge(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    with current_group_case(tmp_path, node_path, monkeypatch, source) as c:
        p = c.preparation
        snapshot = c.actor()
        assert snapshot.project().sealed is not None
        native = c.initialization.native_before
        pair = native.pair()
        assert native.consumed
        assert c.initialization.state.baseline_inputs is not None
        first = InitialStateChecks.model_validate_json(
            p.resource.evidence.read(c.initialization.state.baseline_inputs.initial_ref)
        )
        assert first.checks.status == "pass"
        assert all(
            pair.intent_ref in check.evidence and pair.result_ref in check.evidence
            for check in first.checks.checks
        )
        captured = c.collect()
        assert captured.contract == p.plan.evaluation
        assert c.capture.state.phase == "captured" and c.browser.phase == "closed"
        store, control = p.resource.evidence, p.resource.controls.bind(p.plan.operation)
        evaluated = c.evaluator.evaluate(p.plan.evaluation, store, control)
        # The synthetic Actor deliberately does not create a group. Preserve
        # the original valid failure; this test never reruns for a positive.
        assert evaluated.status == "failure" and evaluated.reward == 0
        assert c.capture.state.selection_ref is not None
        selected = GroupCapturedSelection.model_validate_json(
            store.read(c.capture.state.selection_ref)
        )
        assert selected.browser_record_ref.content_schema == "resource-record/2"
        readonly = RecordedGroupEvaluator(
            c.capture.state.selection_ref, p.preparation.records, p.plan.operation
        )
        assert readonly.evaluate(p.plan.evaluation, store, control) == evaluated
        assert c.backend.channels[0].engine.calls == [
            "start",
            "passive-capture",
            "step",
            "passive-capture",
            "close",
        ]
        with pytest.raises(DispatchAlreadyCommitted):
            c.collect()
        with pytest.raises(DispatchAlreadyCommitted):
            native.record(control)
        rights = UnitCleanupRights(p)
        declaration = TaskFinalizationPlan(
            scope=p.scope,
            browser_close_operation_id="group-close",
            restore_operation_id="group-restore",
            resume_operation_id="group-resume",
            qualification_operation_id="group-reset-facts",
            reset_operation_id="group-safe-reset",
        )
        finalizer = gitlab_group_task_finalization(
            p.plan,
            declaration,
            put(store, declaration),
            p.reset,
            p.preparation,
            lambda: c.browser,
            c.backend.journal,
            lambda: c.capture.state.closure_ref,
            rights,
            rights,
            rights,
            store,
            p.resource.controls,
        )
        reset = close_and_restore(p, finalizer)
        assert finalizer.state.reset_ref == reset
        assert (
            finalizer.state.reset is not None and finalizer.state.reset.status == "safe"
        )
        assert rights.unstarted_calls == 0 and rights.resume_calls == 1
        assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
        assert c.backend.channels[0].engine.calls.count("close") == 1
        # Historical judgment remains reconstructible after live restore.
        assert readonly.evaluate(p.plan.evaluation, store, control) == evaluated


def test_fresh_native_initial_permission_denial_keeps_intent_and_no_dispatch(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = next(iter(GROUP_NATIVE_PINS))
    with current_group_case(tmp_path, node_path, monkeypatch, source) as c:
        original = c.authority.verify

        def permission(
            plan: TaskExecutionPlan,
            declaration: TaskInitializationPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> None:
            # The persisted before intent must exist when its independent
            # fresh permission is denied; earlier browser admission passes.
            if c.initialization.native_before.attempted:
                raise PermissionError("fresh native permission denied")
            original(plan, declaration, operation, control)

        monkeypatch.setattr(c.authority, "verify", permission)
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            c.start()
        assert isinstance(caught.value.primary, PermissionError)
        assert "fresh native permission" in str(caught.value.primary)
        native = c.initialization.native_before
        assert native.recorder is not None
        assert (
            native.recorder.intent_ref is not None
            and native.recorder.result_ref is None
        )
        assert native.recorder.intent_ref in c.initialization.state.references
        assert not native.consumed and c.initialization.state.result is None
        assert c.backend.channels[0].engine.calls == ["start", "passive-capture"]
        with pytest.raises(DispatchAlreadyCommitted):
            native.record(
                c.preparation.resource.controls.bind(c.preparation.plan.operation)
            )
