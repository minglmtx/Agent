"""Source definition/preparation on original fixture RPC facts, no model grant."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_records import (
    SourceQualificationRecordAuthority,
    QualificationTaskDefinition,
    QualificationPreparationFacts,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.map_overlay_records import map_preparation_records
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    NavigationNativeRequestChecks,
)
from map_task_preparation_port_fixtures import preparation_case
from site_instance_fixtures import node_path as node_path


def test_original_source_definition_and_preparation_ports_reject_changed_inputs(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with preparation_case(node_path, monkeypatch, "125732d3658ab4daee02") as p:
        p.acquire()
        p.prepare()
        c, n, state = p.original, p.source.native, p.preparation.state
        assert state.prepare_request is not None and state.prepare_result is not None
        assert state.environment is not None and state.result is not None

        class UnitSourceOwner(OriginalSourceQualificationOwner):
            def require_caller(
                self, op: OperationContext, control: OperationControl
            ) -> None:
                control.checkpoint()
                assert (op.run_id, op.owner_id) == (
                    self.scope.owner.run_id,
                    self.scope.owner.owner_id,
                )

        owner = UnitSourceOwner(
            c.scope,
            c.resource.spec.slurm.execution,
            c.resource.spec.slurm.parent,
            c.resource.evidence,
        )
        native = SourceQualificationNativeAuthority(
            owner,
            c.resource.spec,
            c.resource.op,
            c.resource.journal,
            lambda: None,
            NavigationNativeRequestChecks(),
        )
        facts: QualificationPreparationFacts | None = QualificationPreparationFacts(
            state.prepare_request, state.prepare_result, state.environment
        )
        definition = QualificationTaskDefinition(
            n.binding, n.public, n.private_input_json().encode(), n.spec
        )
        a = SourceQualificationRecordAuthority(
            native, definition, p.site, lambda: facts
        )
        op = state.prepare_request.operation.cleanup(
            "source-record-load", now=c.resource.clock.utcnow(), seconds=120
        )
        control = c.resource.controls.bind(op)
        bindings = EvidenceTaskBindings(c.resource.evidence, c.resource.controls, a)
        assert bindings.load(n.binding_ref, op) == n.binding
        for args in (
            (
                n.binding.model_copy(update={"registration_id": "foreign"}),
                n.public,
                definition.private,
                n.spec.model_dump_json().encode(),
            ),
            (
                n.binding,
                n.public.model_copy(update={"goal": "foreign"}),
                definition.private,
                n.spec.model_dump_json().encode(),
            ),
            (
                n.binding,
                n.public,
                definition.private + b" ",
                n.spec.model_dump_json().encode(),
            ),
            (
                n.binding,
                n.public,
                definition.private,
                n.spec.model_dump_json().encode() + b" ",
            ),
        ):
            with pytest.raises(OwnershipConflict):
                a.verify_binding(*args, op, control)
        records = map_preparation_records(
            c.resource.evidence,
            c.resource.controls,
            bindings,
            a,
            c.configuration,
            p.site.site.instance,
        )
        publication = state.result.publication
        inputs = records.reader.load(publication.selection, op, control)
        receipt = StateReads(c.resource.evidence).parse(
            publication.preparation_ref,
            "preparation-receipt/1",
            PreparationReceipt,
            control,
        )
        assert records.load(publication, op) == p.preparation.records.load(
            publication, op
        )
        with pytest.raises(OwnershipConflict):
            a.verify(
                inputs.model_copy(
                    update={
                        "public_task": n.public.model_copy(update={"goal": "foreign"})
                    }
                ),
                receipt.checks,
                op,
                control,
            )
        facts = None
        with pytest.raises(OwnershipConflict):
            a.verify(inputs, receipt.checks, op, control)
