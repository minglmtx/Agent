"""Same source invocation keeps bodies; every consumer rechecks live premises."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    NavigationNativeRequestChecks,
)
from map_task_preparation_port_fixtures import preparation_case
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("fault", ["none", "owner", "journal", "reference", "storage"])
def test_acquisition_body_delivery_keeps_current_gates(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with preparation_case(node_path, monkeypatch, "125732d3658ab4daee02") as p:
        p.acquire()
        p.prepare()
        c = p.original
        store = c.resource.evidence
        op = c.resource.op.cleanup(
            "source-bodies", now=c.resource.clock.utcnow(), seconds=120
        )
        control = c.resource.controls.bind(op)

        class Owner(OriginalSourceQualificationOwner):
            denied = False
            calls = 0

            def require_caller(
                self, operation: OperationContext, bounded: OperationControl
            ) -> None:
                bounded.checkpoint()
                self.calls += 1
                if self.denied:
                    raise OwnershipConflict("Current caller revoked")
                assert (operation.run_id, operation.owner_id) == (
                    self.scope.owner.run_id,
                    self.scope.owner.owner_id,
                )

        class Current:
            denied = False
            calls = 0

            def check_current(self, bounded: OperationControl) -> None:
                bounded.checkpoint()
                self.calls += 1
                if self.denied:
                    raise OwnershipConflict("Original storage quarantined or revoked")

        owner = Owner(
            c.scope,
            c.resource.spec.slurm.execution,
            c.resource.spec.slurm.parent,
            store,
        )
        current = Current()
        native = SourceQualificationNativeAuthority(
            owner,
            c.resource.spec,
            c.resource.op,
            c.resource.journal,
            lambda: None,
            NavigationNativeRequestChecks(),
            current_evidence=current,
        )
        reads: list[EvidenceRef] = []
        original = store.read

        def observe(ref: EvidenceRef, control: OperationControl) -> bytes:
            reads.append(ref)
            return original(ref, control)

        monkeypatch.setattr(store, "read", observe)
        first = native.require_acquired(op, control)
        assert reads == [first.intent_ref, first.spec_ref]
        owner.denied = fault == "owner"
        current.denied = fault == "storage"
        journal_read = c.resource.journal.read

        def changed(*args: Any, **kwargs: Any) -> Any:
            record = journal_read(*args, **kwargs)
            if fault == "journal":
                return record.model_copy(update={"events": record.events[:-1]})
            if fault == "reference":
                events = list(record.events)
                events[1] = events[1].model_copy(
                    update={
                        "evidence": (
                            first.intent_ref.model_copy(update={"producer": "other"}),
                        )
                    }
                )
                return record.model_copy(update={"events": tuple(events)})
            return record

        with monkeypatch.context() as patch:
            patch.setattr(c.resource.journal, "read", changed)
            if fault == "none":
                assert native.require_acquired(op, control) == first
                assert current.calls == 3
                native.close_input_read()
                assert native.require_acquired(op, control) == first
                assert reads == [first.intent_ref, first.spec_ref] * 2
            else:
                with pytest.raises(OwnershipConflict):
                    native.require_acquired(op, control)
                assert reads == [first.intent_ref, first.spec_ref]
        assert owner.calls >= 2
