"""Frozen initial body -> real capture/terminal/evaluator, synthetic I/O edges."""

from pathlib import Path
from typing import Any, cast
from concurrent.futures import ThreadPoolExecutor
import pytest
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.sites.task_capture_initial_reads import (
    TaskCaptureInitialReads,
)
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.bootstrap.admin_navigation_terminal import (
    read_admin_navigation_terminal,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.initial_observation import (
    InitialObservationInputs,
    InitialObservationSelection,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs
from admin_navigation_terminal_fixtures import terminal_case
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


def chain(error: BaseException) -> list[BaseException]:
    pending = [error]
    seen: list[BaseException] = []
    while pending:
        value = pending.pop()
        if any(value is old for old in seen):
            continue
        seen.append(value)
        for other in (
            value.__cause__,
            value.__context__,
            getattr(value, "primary", None),
        ):
            if isinstance(other, BaseException):
                pending.append(other)
    return seen


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "selection",
        "scope",
        "closed-scope",
        "cancel",
        "deadline",
        "empty-body",
        "body-type",
        "revoked",
    ],
)
def test_capture_and_judgment_reuse_initial_with_fresh_authority_and_cleanup(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with owned_task(
        node_path, monkeypatch, input_handoff=True, capture_initial_handoff=True
    ) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        selected = c.bundle.capture.initials
        assert isinstance(selected, TaskCaptureInitialReads)
        original_read = InitialObservationReader.load
        original_load = selected.load
        original_gate = c.bundle.capture.authority.verify
        loads = []
        gates = []
        denied = False

        def no_repeat(self: InitialObservationReader, *args: Any, **kwargs: Any) -> Any:
            initialized = c.bundle.initialization.original()
            if initialized.state.phase == "initialized":
                pytest.fail(
                    "Capture/judgment reread completed initialization/preparation"
                )
            return original_read(self, *args, **kwargs)

        def gate(*args: Any, **kwargs: Any) -> Any:
            gates.append(1)
            result = original_gate(*args, **kwargs)
            if denied:
                raise PermissionError("Current capture rights revoked after body read")
            return result

        def load(
            selection: Any, operation: OperationContext, control: OperationControl
        ) -> InitialObservationInputs:
            nonlocal denied
            loads.append(operation)
            if fault == "selection":
                selection = selection.model_copy(
                    update={
                        "browser_acquired_ref": selection.browser_acquired_ref.model_copy(
                            update={"producer": "foreign"}
                        )
                    }
                )
            elif fault == "scope":
                operation = operation.model_copy(update={"owner_id": "foreign"})
            elif fault == "closed-scope":
                assert r.inputs is not None
                r.inputs.active = False
            elif fault == "cancel":
                raise OperationStopped("CANCELLED", operation.operation_id)
            elif fault == "deadline":
                raise OperationStopped("DEADLINE_EXCEEDED", operation.operation_id)
            elif fault in {"empty-body", "body-type"}:
                original = c.bundle.initialization.original()
                with monkeypatch.context() as inject:
                    inject.setattr(
                        original,
                        "current_initial_observation",
                        lambda *args: None if fault == "empty-body" else [],
                    )
                    return original_load(selection, operation, control)
            value = original_load(selection, operation, control)
            assert r.inputs is not None and r.inputs.initial is not None
            assert value == r.inputs.initial
            if fault == "revoked":
                denied = True
            return value

        monkeypatch.setattr(InitialObservationReader, "load", no_repeat)
        monkeypatch.setattr(selected, "load", load)
        monkeypatch.setattr(c.bundle.capture.authority, "verify", gate)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert sum(op.operation_id.endswith(".capture") for op in loads) >= 2
            assert any(op == c.p.plan.operation for op in loads)
            assert c.bundle.capture.state.phase == "captured"
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            expected = (
                PermissionError
                if fault == "revoked"
                else (
                    OperationStopped
                    if fault in {"cancel", "deadline"}
                    else ValueError if fault == "body-type" else OwnershipConflict
                )
            )
            assert any(isinstance(e, expected) for e in chain(caught.value))
            assert c.bundle.capture.state.terminal_ref is None
        assert loads and gates and c.native.loader.session.calls == 1
        assert r.inputs is not None and not r.inputs.active and r.inputs.initial is None
        browser = r.browser()
        assert browser is not None and browser.phase == "closed"
        with pytest.raises(OwnershipConflict):
            original_load(
                cast(
                    InitialObservationSelection,
                    c.bundle.initialization.original().state.selection,
                ),
                c.p.plan.operation,
                guard(30),
            )


def test_capture_initial_reader_rejects_different_plan_and_thread(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned_task(
        node_path, monkeypatch, input_handoff=True, capture_initial_handoff=True
    ) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        other = TaskInitializationInputs(
            c.p.plan.model_copy(
                update={"cleanup_seconds": c.p.plan.cleanup_seconds + 1}
            )
        )
        with pytest.raises(OwnershipConflict):
            TaskCaptureInitialReads(c.p.plan, other, c.bundle.initialization.original)
        selected = c.bundle.capture.initials
        assert isinstance(selected, TaskCaptureInitialReads)
        original = selected.load
        checked = []

        def load(
            selection: Any, operation: OperationContext, control: OperationControl
        ) -> InitialObservationInputs:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(original, selection, operation, guard(30))
                with pytest.raises(OwnershipConflict):
                    future.result()
            checked.append(1)
            with pytest.raises(OwnershipConflict):
                original(
                    selection,
                    operation.model_copy(update={"operation_id": "foreign"}),
                    control,
                )
            return original(selection, operation, control)

        monkeypatch.setattr(selected, "load", load)
        assert (
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation).evaluation.status
            == "success"
        )
        assert checked and c.native.loader.session.calls == 1


@pytest.mark.parametrize("negative", [False, True])
def test_admin_terminal_consumes_original_initial_body_without_preparation_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    negative: bool,
) -> None:
    with terminal_case(
        tmp_path, monkeypatch, contracts, negative=negative, current=True
    ) as c:

        def forbidden(*args: Any, **kwargs: Any) -> Any:
            pytest.fail(
                "Terminal attempted to reload completed original initialization"
            )

        monkeypatch.setattr(InitialObservationReader, "load", forbidden)

        class Frozen:
            def load(
                self,
                selection: Any,
                operation: OperationContext,
                control: OperationControl,
            ) -> InitialObservationInputs:
                control.checkpoint()
                assert selection == c.initial.selection
                return cast(InitialObservationInputs, c.initial)

        loaded = read_admin_navigation_terminal(
            c.store,
            c.preparations,
            c.reference,
            c.contract,
            c.operation,
            guard(30),
            initials=Frozen(),
        )
        assert loaded.initial == c.initial and loaded.returned.observation.sequence == 1
        assert loaded.selected is not None


def test_admin_terminal_rejects_wrong_initial_body_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
) -> None:
    with terminal_case(tmp_path, monkeypatch, contracts, current=True) as c:

        class Wrong:
            def load(
                self,
                selection: Any,
                operation: OperationContext,
                control: OperationControl,
            ) -> InitialObservationInputs:
                other = selection.model_copy(
                    update={
                        "browser_acquired_ref": selection.browser_acquired_ref.model_copy(
                            update={"producer": "foreign"}
                        )
                    }
                )
                return cast(
                    InitialObservationInputs,
                    c.initial.model_copy(update={"selection": other}),
                )

        with pytest.raises(OwnershipConflict):
            read_admin_navigation_terminal(
                c.store,
                c.preparations,
                c.reference,
                c.contract,
                c.operation,
                guard(30),
                initials=Wrong(),
            )
