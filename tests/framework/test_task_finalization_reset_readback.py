"""Actual original finalizer uses one proof/readback; legacy port still works."""

from pathlib import Path
import hashlib
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_finalization import (
    TaskFinalizationUnconfirmed,
)
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.reset import ResetReceipt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from task_capture_port_fixtures import capture_case
from task_finalization_port_fixtures import bind_finalization
from site_instance_fixtures import node_path as node_path
from evidence_control_fixtures import EvidenceFixtureStore


@pytest.mark.parametrize("legacy", [False, True])
def test_original_finalizer_single_native_restore_exact_readback_and_legacy_port(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: bool
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.actor()
        case.collect()
        f = bind_finalization(case)
        f.close()
        states = f.finalizer.states
        assert isinstance(states, EvidenceStateRecords)
        graphs: list[Any] = []
        original = states.resets.verify

        def verify(*args: Any, **kwargs: Any) -> Any:
            graphs.append(args[0])
            return original(*args, **kwargs)

        monkeypatch.setattr(states.resets, "verify", verify)
        if legacy:

            class Legacy:
                def publish_baseline(
                    self, receipt: BaselineReceipt, op: OperationContext
                ) -> EvidenceRef:
                    return states.publish_baseline(receipt, op)

                def load_baseline(
                    self, reference: EvidenceRef, op: OperationContext
                ) -> BaselineReceipt:
                    return states.load_baseline(reference, op)

                def publish_reset(
                    self, receipt: ResetReceipt, op: OperationContext
                ) -> EvidenceRef:
                    return states.publish_reset(receipt, op)

                def load_reset(
                    self, reference: EvidenceRef, op: OperationContext
                ) -> ResetReceipt:
                    return states.load_reset(reference, op)

            f.finalizer.states = Legacy()
        else:

            def duplicate_graph(*args: Any) -> Any:
                pytest.fail(
                    "Original finalizer must not reenter independent load_reset after verified publication"
                )

            monkeypatch.setattr(states, "load_reset", duplicate_graph)
        ref = f.restore()
        assert (
            f.finalizer.state.reset_ref == ref and f.finalizer.state.phase == "restored"
        )
        assert len(graphs) == (2 if legacy else 1)
        assert f.resume.calls == 1
        assert [r.action for r in case.initial.preparation.requests] == [
            "snapshot",
            "prepare",
            "restore",
        ]


def test_finalizer_failed_readback_keeps_original_published_reset_and_never_repeats_effects(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        f = bind_finalization(case)
        f.close()
        states = f.finalizer.states
        assert isinstance(states, EvidenceStateRecords)
        assert isinstance(states.store, EvidenceFixtureStore)
        original = states.store.read
        saved: list[EvidenceRef] = []
        first = OSError("original final reset readback failed")

        def read(
            reference: EvidenceRef, control: OperationControl | None = None
        ) -> bytes:
            current = f.finalizer.state.reset
            if (
                reference.content_schema == "reset-receipt/1"
                and current is not None
                and reference.sha256
                == hashlib.sha256(current.model_dump_json().encode()).hexdigest()
            ):
                saved.append(reference)
                raise first
            return original(reference, control=control)

        with monkeypatch.context() as patch:
            patch.setattr(states.store, "read", read)
            with pytest.raises(TaskFinalizationUnconfirmed) as caught:
                f.restore()
        assert len(saved) == 1
        assert isinstance(caught.value.primary, StateCommitUnconfirmed)
        assert caught.value.primary.__cause__ is first
        assert saved[0] in caught.value.references
        assert f.finalizer.state.reset is not None
        assert original(saved[0]) == f.finalizer.state.reset.model_dump_json().encode()
        effects = len(case.initial.preparation.requests), f.resume.calls
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore()
        assert (len(case.initial.preparation.requests), f.resume.calls) == effects
