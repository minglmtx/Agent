"""Current Group cancellation/unknown/immutable evidence boundaries, no grants."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.adapters.sites.task_capture import TaskCaptureUnconfirmed
from lab_generate_skill.bootstrap.gitlab_group_source import GROUP_NATIVE_PINS
from lab_generate_skill.bootstrap.gitlab_group_task_execution import (
    gitlab_group_task_execution,
)
from lab_generate_skill.bootstrap.gitlab_group_task_capture import (
    RecordedGroupEvaluator,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    EvidenceError,
    OwnershipConflict,
)
from lab_generate_skill.domain.lifecycle import (
    ClosureReceipt,
    OperationContext,
    ResourceRecord,
)
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabSiteCapture
from lab_generate_skill.sites.gitlab.group_terminal_schema import (
    GroupCapturedSelection,
    GroupTerminalSelection,
)
from lab_generate_skill.sites.gitlab.tasks.group_initial_capture import (
    group_initial_capture_request,
)
from gitlab_group_current_capture_fixtures import current_group_case
from map_navigation_browser_fixtures import CancelledControl
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path

SOURCE = next(iter(GROUP_NATIVE_PINS))


@pytest.mark.parametrize("bad", [None, {}, [], True, "missing", 1])
def test_group_composition_rejects_wrong_original_input_types_before_effects(
    bad: Any,
) -> None:
    with pytest.raises(TypeError):
        gitlab_group_task_execution(bad, bad, bad, bad)


def test_group_initial_request_rejects_empty_wrong_types_without_browser_or_native(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_group_case(tmp_path, node_path, monkeypatch, SOURCE) as c:
        p = c.preparation
        prepared = p.preparation.state.prepare_request
        assert prepared is not None
        bad: Any
        for bad in (None, {}, [], True, "missing", 1):
            with pytest.raises((TypeError, ValueError)):
                group_initial_capture_request(bad, prepared)
            with pytest.raises((TypeError, ValueError)):
                group_initial_capture_request(c.initialization.declaration, bad)
        assert c.browser.phase == "new" and not c.initialization.native_before.attempted
        assert [r.action for r in p.requests] == ["snapshot", "prepare"]


def test_cancelled_group_initialization_never_opens_browser_or_native_capture(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_group_case(tmp_path, node_path, monkeypatch, SOURCE) as c:
        p = c.preparation
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            c.initialization.start(p.plan, p.operation("starting"), CancelledControl())
        assert isinstance(caught.value.primary, OperationStopped)
        assert not c.initialization.native_before.attempted and not c.backend.channels
        assert c.browser.phase == "new"
        with pytest.raises(DispatchAlreadyCommitted):
            c.start()


def test_native_result_publication_return_lost_retains_candidate_and_original_return(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_group_case(tmp_path, node_path, monkeypatch, SOURCE) as c:
        p, native = c.preparation, c.initialization.native_before
        store = p.resource.evidence
        original = store.put
        committed: list[EvidenceRef] = []

        def lost(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
            *,
            exchange_id: str | None = None,
        ) -> EvidenceRef:
            ref = original(raw, metadata, control, exchange_id=exchange_id)
            if (
                metadata.producer == "site-capture-v1"
                and metadata.content_schema == "site-task-result/1"
            ):
                committed.append(ref)
                raise OSError("Synthetic native result publication return lost")
            return ref

        monkeypatch.setattr(store, "put", lost)
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            c.start()
        assert isinstance(caught.value.primary, OSError)
        assert native.consumed and native.recorder is not None
        assert native.recorder.result is not None and native.recorder.result_ref is None
        assert (
            getattr(caught.value.primary, "group_initial_native_return")
            == native.recorder.result
        )
        assert len(committed) == 1 and committed[0] in caught.value.candidates
        assert (
            store.read(committed[0])
            == native.recorder.result.model_dump_json().encode()
        )
        assert native.recorder.intent_ref in caught.value.references
        assert c.initialization.state.result is None
        for repeat in (
            c.start,
            lambda: native.record(p.resource.controls.bind(p.plan.operation)),
        ):
            with pytest.raises(DispatchAlreadyCommitted):
                repeat()
        assert len(committed) == 1


def test_final_guard_rechecks_source_after_browser_closure_without_replay(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_group_case(tmp_path, node_path, monkeypatch, SOURCE) as c:
        c.actor()
        original = c.browser.close

        def closed(
            operation: OperationContext,
            control: OperationControl,
            *,
            primary: BaseException | None = None,
        ) -> ResourceRecord:
            result = original(operation, control, primary=primary)
            c.capture_authority.denied = True
            return result

        monkeypatch.setattr(c.browser, "close", closed)
        with pytest.raises(TaskCaptureUnconfirmed) as caught:
            c.collect()
        assert isinstance(caught.value.primary, PermissionError)
        assert c.browser.phase == "closed" and caught.value.failed_phase == "guard"
        assert (
            c.capture.state.terminal_ref is not None
            and c.capture.state.closure_ref is not None
        )
        assert c.capture.state.selection_ref is None and c.capture.state.result is None
        with pytest.raises(DispatchAlreadyCommitted):
            c.collect()


def test_readonly_group_rejects_changed_scope_closure_guard_or_initialized_actor(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_group_case(tmp_path, node_path, monkeypatch, SOURCE) as c:
        c.actor()
        c.collect()
        p = c.preparation
        store, control = p.resource.evidence, p.resource.controls.bind(p.plan.operation)
        ref = c.capture.state.selection_ref
        assert ref is not None
        original = c.evaluator.evaluate(p.plan.evaluation, store, control)
        selected = GroupCapturedSelection.model_validate_json(store.read(ref))
        terminal = GroupTerminalSelection.model_validate_json(
            store.read(selected.terminal_ref)
        )
        closure = ClosureReceipt.model_validate_json(
            store.read(selected.browser_closure_ref)
        )
        guard = SiteCaptureIntent.model_validate_json(
            store.read(selected.after.intent_ref)
        )
        foreign_guard = guard.model_copy(
            update={
                "request": guard.request.model_copy(
                    update={
                        "inspection": guard.request.inspection.model_copy(
                            update={
                                "operation": guard.request.operation.model_copy(
                                    update={"operation_id": "foreign-guard"}
                                )
                            }
                        )
                    }
                )
            }
        )
        foreign_actor = terminal.initialized.actor.model_copy(
            update={
                "operation": terminal.initialized.actor.operation.model_copy(
                    update={"operation_id": "foreign-actor"}
                )
            }
        )
        cases = (
            selected.model_copy(
                update={
                    "scope": selected.scope.model_copy(
                        update={"attempt_id": "foreign-attempt"}
                    )
                }
            ),
            selected.model_copy(
                update={
                    "browser_closure_ref": put(
                        store,
                        closure.model_copy(update={"operation_id": "foreign-close"}),
                    )
                }
            ),
            selected.model_copy(
                update={
                    "after": GitlabSiteCapture(
                        intent_ref=put(store, foreign_guard),
                        result_ref=selected.after.result_ref,
                    )
                }
            ),
            selected.model_copy(
                update={
                    "terminal_ref": put(
                        store,
                        terminal.model_copy(
                            update={
                                "initialized": terminal.initialized.model_copy(
                                    update={"actor": foreign_actor}
                                )
                            }
                        ),
                    )
                }
            ),
        )
        for case in cases:
            reviewer = RecordedGroupEvaluator(
                put(store, case), p.preparation.records, p.plan.operation
            )
            with pytest.raises((EvidenceError, OwnershipConflict, ValueError)):
                reviewer.evaluate(p.plan.evaluation, store, control)
        assert c.evaluator.evaluate(p.plan.evaluation, store, control) == original
        assert c.backend.channels[0].engine.calls.count("step") == 1
