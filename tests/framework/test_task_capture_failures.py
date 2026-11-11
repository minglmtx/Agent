"""Original capture cannot redispatch on invalid trace, partial save or closure."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_capture import TaskCaptureUnconfirmed
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case


@pytest.mark.parametrize(
    "fault",
    [
        "task-denied",
        "page-denied",
        "site-denied",
        "empty-inputs",
        "wrong-inputs",
        "stale-return",
        "wrong-role",
    ],
)
def test_unqualified_input_or_source_cannot_complete_capture(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.actor()
        c = case.capture
        inputs = c.inputs
        if fault == "task-denied":
            case.authority.denied = True
        elif fault == "page-denied":
            case.initial.capture_authority.denied = True
        elif fault == "site-denied":
            case.site_authority.denied = True
        elif fault in ("empty-inputs", "wrong-inputs"):

            def invalid(control: OperationControl) -> Any:
                return None if fault == "empty-inputs" else []

            monkeypatch.setattr(c, "inputs", invalid)
        elif fault == "stale-return":
            case.initial.browser.session.last_return_ref = None
        else:

            def role(control: OperationControl) -> Any:
                original = inputs(control)
                actor = original.initialized.actor
                return original.model_copy(
                    update={
                        "initialized": original.initialized.model_copy(
                            update={
                                "actor": actor.model_copy(
                                    update={
                                        "model_allocation": actor.browser_allocation
                                    }
                                )
                            }
                        )
                    }
                )

            monkeypatch.setattr(c, "inputs", role)
        with pytest.raises(TaskCaptureUnconfirmed) as caught:
            case.collect()
        assert case.site_authority.calls == 0 and c.state.result is None
        assert case.initial.browser.phase == (
            "closed" if fault == "site-denied" else "open"
        )
        assert case.initial.backend.calls.count("actual_action") == 1
        with pytest.raises(DispatchAlreadyCommitted):
            case.collect()
        if fault in ("page-denied", "site-denied"):
            assert any(
                ref.content_schema.endswith("capture-intent/1")
                or ref.content_schema == "site-capture-intent/2"
                for ref in caught.value.references
            )


@pytest.mark.parametrize(
    "schema",
    [
        "browser-capture-intent/1",
        "browser-capture-result/1",
        "map-navigation-terminal-selection/1",
        "closure-receipt/1",
        "site-capture-intent/2",
        "site-task-result/1",
        "map-navigation-evidence/1",
    ],
)
def test_complete_commit_lost_ack_retains_candidate_and_never_repeats(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.actor()
        store = case.initial.preparation.original.resource.evidence
        original = store.put
        persisted: list[tuple[EvidenceRef, bytes]] = []

        def lose(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
        ) -> EvidenceRef:
            ref = original(raw, metadata, control)
            if metadata.content_schema == schema:
                persisted.append((ref, raw))
                raise TimeoutError(
                    "synthetic terminal acknowledgement lost after complete CAS save"
                )
            return ref

        with monkeypatch.context() as patch:
            patch.setattr(store, "put", lose)
            with pytest.raises(TaskCaptureUnconfirmed) as caught:
                case.collect()
        assert isinstance(caught.value.primary, TimeoutError)
        assert len(persisted) == 1
        ref, raw = persisted[0]
        assert store.read(ref) == raw
        assert ref in (*caught.value.references, *caught.value.candidates)
        before = case.site_authority.calls
        with pytest.raises(DispatchAlreadyCommitted):
            case.collect()
        assert case.site_authority.calls == before and case.capture.state.result is None


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_stop_after_terminal_keeps_full_refs_and_defers_original_cleanup(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.actor()
        original = case.capture.records.verify_terminal

        def stop(
            ref: EvidenceRef, operation: OperationContext, control: OperationControl
        ) -> None:
            original(ref, operation, control)
            raise OperationStopped(reason, operation.operation_id)

        monkeypatch.setattr(case.capture.records, "verify_terminal", stop)
        with pytest.raises(TaskCaptureUnconfirmed) as caught:
            case.collect()
        assert isinstance(caught.value.primary, OperationStopped)
        assert any(
            ref.content_schema == "map-navigation-terminal-selection/1"
            for ref in caught.value.references
        )
        assert case.initial.browser.phase == "open" and case.site_authority.calls == 0
        with pytest.raises(DispatchAlreadyCommitted):
            case.collect()


def test_unconfirmed_close_forbids_guard_and_only_reconciles_original_ending(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.actor()
        browser = case.initial.browser
        original = browser.close

        def lost(
            operation: OperationContext, control: OperationControl, **kwargs: Any
        ) -> Any:
            record = original(operation, control, **kwargs)
            error = OwnershipConflict(
                "Synthetic original closed acknowledgement unconfirmed"
            )
            setattr(error, "browser_resource_ending_ref", record.events[-1].evidence[0])
            raise error

        with monkeypatch.context() as patch:
            patch.setattr(browser, "close", lost)
            with pytest.raises(TaskCaptureUnconfirmed) as caught:
                case.collect()
        assert case.site_authority.calls == 0 and case.capture.state.result is None
        assert any(
            ref.content_schema == "browser-resource-fact/1"
            for ref in caught.value.references
        )
        finishes = case.initial.backend.resource.channels[0].finishes
        op = browser.operation.cleanup(
            "unit-original-close-read-only", now=datetime.now(timezone.utc), seconds=20
        )
        assert browser.close(op, browser.controls.bind(op)).state == "closed"
        assert case.initial.backend.resource.channels[0].finishes == finishes
        with pytest.raises(DispatchAlreadyCommitted):
            case.collect()
