"""Owned cleanup boundaries; all physical/source/native premises are synthetic."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_finalization import (
    TaskFinalizationUnconfirmed,
)
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case
from task_finalization_port_fixtures import bind_finalization


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("revoked", [False, True])
def test_post_close_metadata_failure_retains_facts_and_rechecks_before_restore(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    started: bool,
    revoked: bool,
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        if started:
            case.actor()
        finalization = bind_finalization(case)
        original = finalization.authority.verify
        primary = TimeoutError("unit metadata deadline after completed browser close")
        fail_once = True

        def late_metadata(*args: Any, **kwargs: Any) -> None:
            nonlocal fail_once
            original(*args, **kwargs)
            if fail_once:
                fail_once = False
                raise primary

        monkeypatch.setattr(finalization.authority, "verify", late_metadata)
        with pytest.raises(TaskFinalizationUnconfirmed) as caught:
            finalization.close()
        assert caught.value.primary is primary
        assert caught.value.failed_phase == "close-admission"
        closed = caught.value.known_closed
        assert closed is not None
        assert finalization.finalizer.state.phase == "close-admission-unconfirmed"
        assert all(value.status == "closed" for value in closed.closures)
        finalization.closed = closed
        finalization.authority.denied = revoked
        before = len(finalization.authority.calls)
        if revoked:
            with pytest.raises(TaskFinalizationUnconfirmed) as denied:
                finalization.restore()
            assert isinstance(denied.value.primary, PermissionError)
            assert finalization.resume.calls == 0
            assert [r.action for r in case.initial.preparation.requests] == [
                "snapshot",
                "prepare",
            ]
        else:
            finalization.restore()
            assert finalization.finalizer.state.reset is not None
            assert finalization.finalizer.state.reset.status == "safe"
            assert finalization.resume.calls == 1
            assert [r.action for r in case.initial.preparation.requests] == [
                "snapshot",
                "prepare",
                "restore",
            ]
        assert len(finalization.authority.calls) > before
        with pytest.raises(DispatchAlreadyCommitted):
            finalization.close()
        assert finalization.unstarted.calls == (0 if started else 1)


@pytest.mark.parametrize("started", [False, True])
def test_owned_browser_or_independent_nonstart_closes_before_original_restore(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, started: bool
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        if started:
            case.initial.start()
        f = bind_finalization(case)
        closed = f.close()
        assert all(r.status == "closed" for r in closed.closures)
        assert f.unstarted.calls == (0 if started else 1)
        if started:
            assert case.initial.browser.phase == "closed"
            assert case.initial.backend.resource.channels[0].finishes == 1
        else:
            assert case.initial.backend.engines == []
            assert case.initial.browser.phase == "new"
        f.restore()
        assert f.finalizer.state.reset is not None
        assert f.finalizer.state.reset.status == "safe" and f.resume.calls == 1


@pytest.mark.parametrize(
    "fault",
    [
        "nonstart-denied",
        "missing-handle",
        "unknown-close",
        "source-denied",
        "declaration-changed",
    ],
)
def test_absence_unknown_or_missing_authority_never_admits_restore(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        if fault != "nonstart-denied":
            case.initial.start()
        f = bind_finalization(case)
        p = case.initial.preparation
        if fault == "nonstart-denied":
            f.unstarted.denied = True
        elif fault == "missing-handle":
            monkeypatch.setattr(f.finalizer.browser, "browser", lambda: None)
        elif fault == "unknown-close":

            def unknown(*args: Any, **kwargs: Any) -> Any:
                raise TimeoutError("Synthetic original browser ending unknown")

        elif fault == "source-denied":
            f.authority.denied = True
        else:
            f.finalizer.declaration_ref = put(p.original.resource.evidence, p.reset)
        # Keep the original fixture owner available to finish its own cleanup.
        if fault == "unknown-close":
            with monkeypatch.context() as patch:
                patch.setattr(case.initial.browser, "close", unknown)
                with pytest.raises(TaskFinalizationUnconfirmed):
                    f.close()
        else:
            with pytest.raises(TaskFinalizationUnconfirmed):
                f.close()
        state = f.finalizer.state
        assert state.reset_ref is None and not state.restore_attempted
        assert f.resume.calls == 0
        assert [r.action for r in p.requests] == ["snapshot", "prepare"]
        if fault in ("source-denied", "declaration-changed"):
            assert case.initial.browser.phase == "closed"
            assert case.initial.backend.resource.channels[0].finishes == 1
            assert f.finalizer.browser.references
            assert state.phase == "close-admission-unconfirmed"
            assert state.closed is not None
            assert all(c.status == "closed" for c in state.closed.closures)
            assert state.closed.closure_refs
            assert all(
                ref in f.finalizer.browser.references
                for ref in state.closed.closure_refs
            )
            f.closed = state.closed
            with pytest.raises(TaskFinalizationUnconfirmed):
                f.restore()
            assert state.restore_attempted and state.reset_ref is None
            assert state.restore_request is None and f.resume.calls == 0
            assert [r.action for r in p.requests] == ["snapshot", "prepare"]
        else:
            assert state.closed is None
        if fault == "missing-handle":
            assert f.unstarted.calls == 0 and case.initial.browser.phase == "open"
        with pytest.raises(DispatchAlreadyCommitted):
            f.close()


@pytest.mark.parametrize("fault", ["scope", "parent", "reset"])
def test_wrong_domain_is_rejected_before_physical_close(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.initial.start()
        f = bind_finalization(case)
        p = case.initial.preparation
        op, reset = f.operation("closing"), p.reset
        if fault == "scope":
            op = op.model_copy(update={"owner_id": "another-owner"})
        elif fault == "parent":
            op = op.model_copy(update={"parent_operation_id": "another-task"})
        else:
            reset = reset.model_copy(update={"parent_operation_id": "another-prepare"})
        with pytest.raises(OwnershipConflict):
            f.finalizer.close(p.plan, reset, op, p.original.resource.controls.bind(op))
        assert not f.finalizer.state.close_attempted
        assert case.initial.browser.phase == "open" and f.unstarted.calls == 0


@pytest.mark.parametrize(
    "field",
    [
        "snapshot_ref",
        "snapshot_request",
        "snapshot_request_ref",
        "snapshot_result_ref",
        "environment_selection_ref",
        "prepare_request",
        "prepare_result",
        "prepare_request_ref",
        "prepare_result_ref",
    ],
)
def test_missing_original_fact_never_dispatches_restore_or_resume(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        f = bind_finalization(case)
        f.close()
        p = case.initial.preparation
        monkeypatch.setattr(p.preparation.state, field, None)
        with pytest.raises(TaskFinalizationUnconfirmed) as caught:
            f.restore()
        assert isinstance(caught.value.primary, OwnershipConflict)
        assert [r.action for r in p.requests] == ["snapshot", "prepare"]
        assert f.resume.calls == 0 and f.finalizer.state.reset_ref is None
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore()


@pytest.mark.parametrize(
    "schema",
    [
        "site-task-request/2",
        "site-task-result/1",
        "site-resume-request/1",
        "site-resume-intent/1",
        "site-resume-result/1",
        "reset-selection/1",
        "task-reset/1",
        "environment-reset/1",
        "reset-health/1",
        "reset-receipt/1",
    ],
)
def test_complete_publication_lost_ack_keeps_bytes_and_never_redispatches(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        f = bind_finalization(case)
        f.close()
        store = case.initial.preparation.original.resource.evidence
        original = store.put
        saved: list[tuple[EvidenceRef, bytes]] = []

        def lose(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
        ) -> EvidenceRef:
            ref = original(raw, metadata, control)
            if metadata.content_schema == schema:
                saved.append((ref, raw))
                raise TimeoutError("Synthetic complete original cleanup CAS ack lost")
            return ref

        with monkeypatch.context() as patch:
            patch.setattr(store, "put", lose)
            with pytest.raises(TaskFinalizationUnconfirmed) as caught:
                f.restore()
        assert len(saved) == 1
        ref, raw = saved[0]
        assert store.read(ref) == raw
        assert ref in (*caught.value.references, *caught.value.candidates)
        count = len(case.initial.preparation.requests), f.resume.calls
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore()
        assert (len(case.initial.preparation.requests), f.resume.calls) == count
        assert (
            f.finalizer.state.phase == "quarantined"
            and f.finalizer.state.reset_ref is None
        )


@pytest.mark.parametrize("stage", ["restore", "resume"])
def test_native_return_lost_keeps_intent_no_retry_or_safe_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        f = bind_finalization(case)
        f.close()
        site = case.initial.preparation.site
        if stage == "restore":
            original = site.tasks.execute_task

            def lost_restore(*args: Any, **kwargs: Any) -> Any:
                original(*args, **kwargs)
                raise TimeoutError("Synthetic native restore response lost")

            monkeypatch.setattr(site.tasks, "execute_task", lost_restore)
        else:
            original_resume = site.resume.resume_frontend

            def lost_resume(*args: Any, **kwargs: Any) -> Any:
                original_resume(*args, **kwargs)
                raise TimeoutError("Synthetic original resume response lost")

            monkeypatch.setattr(site.resume, "resume_frontend", lost_resume)
        with pytest.raises(TaskFinalizationUnconfirmed) as caught:
            f.restore()
        assert isinstance(caught.value.primary, TimeoutError)
        assert f.finalizer.state.restore_request_ref in caught.value.references
        assert any(
            r.content_schema == "site-resume-intent/1" for r in caught.value.references
        ) == (stage == "resume")
        assert f.finalizer.state.reset_ref is None
        count = len(case.initial.preparation.requests), f.resume.calls
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore()
        assert (len(case.initial.preparation.requests), f.resume.calls) == count


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_stop_during_restore_preserves_closed_domain_and_no_native_request(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        f = bind_finalization(case)
        closed = f.close()
        original = f.authority.verify

        def stop(
            plan: Any,
            declaration: Any,
            references: tuple[EvidenceRef, ...],
            operation: OperationContext,
            control: OperationControl,
        ) -> None:
            original(plan, declaration, references, operation, control)
            raise OperationStopped(reason, operation.operation_id)

        monkeypatch.setattr(f.authority, "verify", stop)
        with pytest.raises(TaskFinalizationUnconfirmed) as caught:
            f.restore()
        assert isinstance(caught.value.primary, OperationStopped)
        assert caught.value.known_closed == closed and caught.value.known_reset is None
        assert f.resume.calls == 0
        assert [r.action for r in case.initial.preparation.requests] == [
            "snapshot",
            "prepare",
        ]
