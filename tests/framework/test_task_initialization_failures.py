"""No replay on original source mismatch, cancellation or partial publication."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_group_cases import SOURCES
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from task_initialization_port_fixtures import (
    initialization_case,
    InitializationPortCase,
)


def refreeze(case: InitializationPortCase) -> None:
    init = case.initialization
    init.declaration_ref = put(
        case.preparation.original.resource.evidence, init.declaration
    )


@pytest.mark.parametrize(
    "fault", ["source-context", "skill-digest", "browser-origin", "revision-round"]
)
def test_changed_original_identity_is_rejected_before_browser(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        p, init = case.preparation, case.initialization
        if fault in ("source-context", "skill-digest"):
            intent = p.plan.intent.model_copy(
                update=(
                    {
                        "public_context_ref": p.plan.intent.public_context_ref.model_copy(
                            update={"sha256": "f" * 64}
                        )
                    }
                    if fault == "source-context"
                    else {"skill_digest": "f" * 64}
                )
            )
            p.plan = p.plan.model_copy(update={"intent": intent})
            init.plan = p.plan
        elif fault == "revision-round":
            init.declaration = init.declaration.model_copy(
                update={
                    "actor": init.declaration.actor.model_copy(
                        update={"revision_round": 1}
                    )
                }
            )
            refreeze(case)
        else:
            b = case.browser
            task = b.spec.configuration.spec.task.model_copy(
                update={"start_url": "http://127.0.0.1:1/"}
            )
            config = b.spec.configuration.model_copy(
                update={
                    "spec": b.spec.configuration.spec.model_copy(update={"task": task})
                }
            )
            b.spec = b.spec.model_copy(update={"configuration": config})
            init.declaration = init.declaration.model_copy(
                update={"browser_spec_ref": put(p.original.resource.evidence, b.spec)}
            )
            refreeze(case)
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            case.start()
        assert caught.value.failed_phase == "admission"
        assert case.browser.phase == "new" and case.backend.engines == []
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()


@pytest.mark.parametrize(
    "schema",
    [
        "browser-capture-intent/1",
        "browser-capture-result/1",
        "initial-state-checks/1",
        "baseline-receipt/1",
        "equivalence-receipt/1",
    ],
)
def test_postcommit_ack_loss_retains_complete_candidate_without_redispatch(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        store = case.preparation.original.resource.evidence
        original = store.put
        persisted: list[tuple[EvidenceRef, bytes]] = []

        def lose_ack(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
        ) -> EvidenceRef:
            ref = original(raw, metadata, control)
            if metadata.content_schema == schema:
                persisted.append((ref, raw))
                raise TimeoutError(
                    "synthetic CAS acknowledgement lost after full commit"
                )
            return ref

        with monkeypatch.context() as patch:
            patch.setattr(store, "put", lose_ack)
            with pytest.raises(TaskInitializationUnconfirmed) as caught:
                case.start()
        assert isinstance(caught.value.primary, TimeoutError)
        assert len(persisted) == 1
        ref, raw = persisted[0]
        assert store.read(ref) == raw
        assert ref in (*caught.value.references, *caught.value.candidates)
        assert case.browser.phase == "open" and case.initialization.state.result is None
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()
        assert len(persisted) == 1 and case.backend.calls.count("project") == 1


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_cancellation_after_initial_publication_keeps_original_for_close(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        init = case.initialization
        original = getattr(init.measurements, "record_complete")

        def stop(
            selection: InitialObservationSelection, control: OperationControl
        ) -> EvidenceRef:
            ref = original(selection, control).reference
            failure = OperationStopped(
                reason, init.declaration.initial_operation.operation_id
            )
            setattr(failure, "initial_checks_reference", ref)
            raise failure

        monkeypatch.setattr(init.measurements, "record_complete", stop)
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            case.start()
        assert isinstance(caught.value.primary, OperationStopped)
        assert caught.value.primary.reason_code == reason
        assert any(
            r.content_schema == "initial-state-checks/1"
            for r in caught.value.references
        )
        assert case.browser.phase == "open" and init.state.baseline_ref is None
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()


@pytest.mark.parametrize(
    "fault", ["empty-result", "wrong-type", "stale-first-return", "comparison-denied"]
)
def test_invalid_or_stale_measurement_cannot_admit_actor(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with initialization_case(node_path, monkeypatch, SOURCES[0]) as case:
        init = case.initialization
        original = getattr(init.measurements, "record_complete")

        def measure(
            selection: InitialObservationSelection, control: OperationControl
        ) -> Any:
            if fault == "empty-result":
                return None
            if fault == "wrong-type":
                return {"unexpected": []}
            if fault == "stale-first-return":
                op = init.declaration.browser_acquisition.model_copy(
                    update={"operation_id": "unit-unexpected-action-before-initial"}
                )
                case.browser.session.step(
                    BrowserAction(
                        action_id="unit-unexpected",
                        protocol_id="browsergym-highlevel-v1",
                        name="click",
                        payload="click('1')",
                    ),
                    op,
                    control=control,
                )
            return original(selection, control)

        if fault == "comparison-denied":
            case.context_authority.denied_equivalence = True
        else:
            monkeypatch.setattr(init.measurements, "record_complete", measure)
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            case.start()
        assert init.state.result is None and case.browser.phase == "open"
        if fault == "comparison-denied":
            assert init.state.baseline_ref is not None
        if fault == "stale-first-return":
            assert isinstance(caught.value.primary, OwnershipConflict)
            assert getattr(init.measurements, "capture") is None
            assert case.backend.calls.count("project") == 2
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()


def test_foreign_start_does_not_consume_or_execute_original_initialization(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        p = case.preparation
        wrong = p.operation("starting").model_copy(
            update={"attempt_id": "foreign", "operation_id": "foreign-start-probe"}
        )
        with pytest.raises(OwnershipConflict):
            case.initialization.start(
                p.plan, wrong, p.original.resource.controls.bind(wrong)
            )
        assert case.initialization.state.phase == "new" and case.backend.engines == []
        assert case.start().actor.scope == p.declaration.scope
