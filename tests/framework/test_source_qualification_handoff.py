"""Original acquired resource and state consumer share only an exact same-call ref."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_state import (
    SourceQualificationStateAuthority,
    QualificationStateSelections,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    NavigationNativeRequestChecks,
)
from map_task_preparation_port_fixtures import preparation_case
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("alias", [False, True])
def test_actual_qualification_state_handoff_reads_exact_spec_once_and_new_ref_fresh(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, alias: bool
) -> None:
    with preparation_case(node_path, monkeypatch, "125732d3658ab4daee02") as p:
        p.acquire()
        p.prepare()
        c, state = p.original, p.preparation.state
        assert state.environment_selection_ref is not None
        op = c.resource.op.cleanup(
            "qualification-handoff-read", now=c.resource.clock.utcnow(), seconds=120
        )
        control = c.resource.controls.bind(op)
        store = c.resource.evidence
        environment = StateReads(store).parse(
            state.environment_selection_ref,
            "environment-selection/1",
            EnvironmentSelection,
            control,
        )
        selected_ref = state.environment_selection_ref
        if alias:
            ref = store.put(
                c.resource.spec.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="site-resource-spec/1",
                    visibility="private",
                    producer="different-complete-reference",
                ),
                control,
            )
            assert (
                ref.sha256 == environment.site_spec_ref.sha256
                and ref != environment.site_spec_ref
            )
            environment = environment.model_copy(update={"site_spec_ref": ref})
            selected_ref = store.put(
                environment.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="environment-selection/1",
                    visibility="private",
                    producer="qualification-handoff-fixture",
                ),
                control,
            )

        class UnitOwner(OriginalSourceQualificationOwner):
            denied = False
            calls = 0

            def require_caller(
                self, operation: OperationContext, bounded: OperationControl
            ) -> None:
                bounded.checkpoint()
                self.calls += 1
                if self.denied:
                    raise OwnershipConflict("Original source caller revoked")
                assert (operation.run_id, operation.owner_id) == (
                    self.scope.owner.run_id,
                    self.scope.owner.owner_id,
                )

        owner = UnitOwner(
            c.scope,
            c.resource.spec.slurm.execution,
            c.resource.spec.slurm.parent,
            store,
        )
        native = SourceQualificationNativeAuthority(
            owner,
            c.resource.spec,
            c.resource.op,
            c.resource.journal,
            lambda: None,
            NavigationNativeRequestChecks(),
        )
        known = QualificationStateSelections(environment, selected_ref)
        authority = SourceQualificationStateAuthority(native, lambda: known)
        reads: list[EvidenceRef] = []
        original_read = store.read

        def observe(ref: EvidenceRef, control: OperationControl) -> bytes:
            reads.append(ref)
            return original_read(ref, control)

        monkeypatch.setattr(store, "read", observe)
        for _ in range(2):
            start = len(reads)
            authority.verify(c.scope, selected_ref, "environment", op, control)
            actual = reads[start:]
            assert len(
                [r for r in actual if r.content_schema == "site-resource-spec/1"]
            ) == (2 if alias else 1)
            assert (
                len(
                    [
                        r
                        for r in actual
                        if r.content_schema == "resource-acquisition-intent/1"
                    ]
                )
                == 1
            )
        owner.denied = True
        before = len(reads)
        with pytest.raises(OwnershipConflict):
            authority.verify(c.scope, selected_ref, "environment", op, control)
        assert len(reads) == before and owner.calls == 3
        owner.denied = False
        original_journal_read = c.resource.journal.read

        def closed(*args: Any, **kwargs: Any) -> Any:
            record = original_journal_read(*args, **kwargs)
            return record.model_copy(update={"events": record.events[:-1]})

        with monkeypatch.context() as patch:
            patch.setattr(c.resource.journal, "read", closed)
            with pytest.raises(OwnershipConflict):
                authority.verify(c.scope, selected_ref, "environment", op, control)
            assert len(reads) == before
