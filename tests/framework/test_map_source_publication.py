"""Closed source publication on retained real facts, synthetic caller permission.

Original 4888671 bytes/identities/artifacts remain read-only. No new owner/job is
substituted in those facts. Only this test's caller permission and writable CAS
are synthetic; the production default owner would reject the ended controller.
No source initialization, site, browser, model or task request is repeated.
"""

import json
from types import SimpleNamespace
from typing import Any, cast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionInputs
from lab_generate_skill.domain.preparation_read import PreparationReadRequest
from lab_generate_skill.domain.baseline_read import BaselineReadRequest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.map_source_publication import (
    ClosedMapQualificationFacts,
    publish_closed_map_qualification,
)
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.public_context import (
    PublicContextReceipt,
    PublicContextInputs,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.closed_source_read import (
    ClosedMapReadMaterial,
    ClosedSourceMaterial,
    ClosedSourceBindingInput,
    ClosedSourcePublicationInput,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.storage.readonly_evidence import (
    ReadOnlyEvidence as FixedReadOnlyEvidence,
)
from lab_generate_skill.bootstrap.map_closed_source import (
    closed_map_source_contexts,
    ClosedMapSourceDeclarations,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from map_closed_source_fixtures import original_closed_source
from source_review_records import ReadOnlyEvidence
from evidence_control_fixtures import EvidenceFixtureStore
from test_resource_journal import NoCancellation

E = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1"
)


@pytest.mark.parametrize(
    "mode", ["original", "supervised", "proof_failure", "partial_write"]
)
def test_closed_measurements_publish_through_original_verifier_without_source_replay(
    tmp_path: Path,
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qualification = json.loads(
        (E / "source-qualification-4888671/source-only-qualification.json").read_bytes()
    )
    facts_path = Path(qualification["facts_path"])
    original = ReadOnlyEvidence(Path(qualification["evidence_root"]))
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    scope_owner = qualification["source_scope"]["owner"]
    op = OperationContext(
        operation_id="unit-original-closed-source-publication",
        run_id=scope_owner["run_id"],
        owner_id=scope_owner["owner_id"],
        deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
    )
    control = controls.bind(op)
    d = original_closed_source(facts_path, original, control)
    raw = json.loads(facts_path.read_bytes())
    read = StateReads(original)
    previous = read.parse(
        d.context_ref, "public-context-receipt/1", PublicContextReceipt, control
    )
    baseline = read.parse(
        previous.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    reset = read.parse(previous.reset_ref, "reset-receipt/1", ResetReceipt, control)
    initial = read.parse(
        EvidenceRef.model_validate(raw["prepared_browser"]["baseline_inputs_ref"]),
        "baseline-inputs/1",
        BaselineInputs,
        control,
    )
    restoration = read.parse(
        EvidenceRef.model_validate(raw["qualified_source"]["reset_inputs_ref"]),
        "reset-inputs/1",
        ResetInputs,
        control,
    )
    root = tmp_path / "new-cas"
    root.mkdir()

    class UnitOverlay:
        def __init__(self) -> None:
            self.local = EvidenceFixtureStore(root)
            self.written: set[str] = set()

        def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
            if ref.sha256 in self.written:
                return self.local.read(ref, control)
            return original.read(ref, control)

        def put(
            self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            ref = self.local.put(data, metadata, control)
            self.written.add(ref.sha256)
            if mode == "partial_write" and len(self.written) == 2:
                raise OSError("Original summary commit acknowledgement lost")
            return ref

    store = UnitOverlay()

    class UnitOriginalCaller(OriginalSourceQualificationOwner):
        def require_caller(
            self, operation: OperationContext, control: OperationControl
        ) -> None:
            control.checkpoint()
            if (operation.run_id, operation.owner_id) != (
                self.scope.owner.run_id,
                self.scope.owner.owner_id,
            ):
                raise OwnershipConflict("Explicit unit original caller changed")

    owner = UnitOriginalCaller(
        previous.scope, d.site.slurm.execution, d.site.slurm.parent, store
    )

    class UnitRead(ClosedSourceReadTransport):
        """Only the remote/kernel boundary is unit; original graph rules run."""

        def __init__(self) -> None:
            self.checked = False

        def require_current(
            self, material: ClosedSourceMaterial, operation: OperationContext
        ) -> None:
            assert material.site.token.owner == owner.scope.owner
            assert operation.run_id == owner.scope.owner.run_id

        def read(
            self,
            material: ClosedSourceMaterial,
            control: OperationControl,
            *,
            binding: ClosedSourceBindingInput | None = None,
            publication: ClosedSourcePublicationInput | None = None,
            plan_inputs: RunPlan | None = None,
            binding_reference: EvidenceRef | None = None,
            execution_plan: TaskExecutionPlan | None = None,
            context_inputs: bool = False,
            actor_inputs: ActorAcquisitionInputs | None = None,
            preparation_read: PreparationReadRequest | None = None,
            baseline_read: BaselineReadRequest | None = None,
        ) -> PublicContextReceipt:
            assert (
                baseline_read is None
            )  # Publication-only transport; no baseline role.
            assert (
                preparation_read is None
            )  # This unit transport has no preparation role.
            assert actor_inputs is None  # This unit reader cannot prove Actor bodies.
            assert execution_plan is None  # Publication-only transport.
            assert binding_reference is None  # Publication-only unit transport.
            assert (
                plan_inputs is None
            )  # This publication-only unit transport has no plan role.
            assert isinstance(material, ClosedMapReadMaterial)
            assert binding is None
            if publication is not None:
                assert not store.written
                if mode == "proof_failure":
                    raise PermissionError("Original installed source proof rejected")
                proposed = FixedReadOnlyEvidence(
                    Path(qualification["evidence_root"]),
                    max_object_bytes=64 * 1024**2,
                    proposed=publication,
                )
                # Use typed original declarations, not model_dump dictionaries.
                declarations = ClosedMapSourceDeclarations(
                    **{k: getattr(material, k) for k in vars(d)}
                )
                reader = closed_map_source_contexts(
                    declarations, proposed, controls, op
                )
                self.checked = True
                return reader.load_context(material.context_ref, op)
            assert self.checked
            declarations = ClosedMapSourceDeclarations(
                **{k: getattr(material, k) for k in vars(d)}
            )
            reader = closed_map_source_contexts(declarations, store, controls, op)
            if context_inputs:
                result, inputs = reader.load_context_inputs(material.context_ref, op)
                self.last_reply = cast(Any, SimpleNamespace(context_inputs=inputs))
                return result
            return reader.load_context(material.context_ref, op)

    transport = None if mode == "original" else UnitRead()
    facts = ClosedMapQualificationFacts(
        environment_ref=d.environment_ref,
        reset_selection_ref=d.reset_ref,
        initial=d.initial,
        initial_capture=d.initial_capture,
        site=d.site,
        browser=d.browser,
        site_record=d.site_record,
        browser_record=d.browser_record,
        baseline_inputs=initial,
        baseline=baseline,
        reset_inputs=restoration,
        reset=reset,
    )
    from lab_generate_skill.bootstrap.map_closed_source import ClosedMapSourceContexts

    original_load = ClosedMapSourceContexts.load_context_inputs
    loads: list[EvidenceRef] = []

    def verified(
        self: ClosedMapSourceContexts, ref: EvidenceRef, operation: OperationContext
    ) -> tuple[PublicContextReceipt, PublicContextInputs]:
        result = original_load(self, ref, operation)
        loads.append(ref)
        return result

    monkeypatch.setattr(ClosedMapSourceContexts, "load_context_inputs", verified)
    if mode in ("proof_failure", "partial_write"):
        with pytest.raises(PermissionError if mode == "proof_failure" else OSError):
            publish_closed_map_qualification(
                owner,
                facts,
                op,
                controls,
                clock,
                metadata_seconds=600,
                source_reads=transport,
            )
        assert len(store.written) == (0 if mode == "proof_failure" else 2)
        assert not owner._sealed
        return
    published = publish_closed_map_qualification(
        owner, facts, op, controls, clock, metadata_seconds=600, source_reads=transport
    )
    assert loads == [published.declarations.context_ref] * (
        1 if mode == "original" else 2
    )
    assert published.inputs.baseline_inputs == initial
    assert published.inputs.reset_inputs == restoration
    assert published.receipt.scope == previous.scope
    assert published.receipt.baseline_ref == previous.baseline_ref
    assert published.receipt.reset_ref == previous.reset_ref
    assert (
        published.contexts.load_context(published.declarations.context_ref, op)
        == published.receipt
    )
    assert published.declarations.site_record == d.site_record
    assert published.declarations.browser_record == d.browser_record
    with pytest.raises(OwnershipConflict):
        publish_closed_map_qualification(
            owner, facts, op, controls, clock, metadata_seconds=600
        )
