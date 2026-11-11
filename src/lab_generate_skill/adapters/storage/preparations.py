"""Publish/load existing preparation contracts from actual immutable RPC facts.

No site calls. Partial publications retain all returned references. Explicit
reconciliation rechecks original bytes/authority and uses CAS, never prepares
again. This does not issue BaselineReceipt or permission to invoke the Actor.
"""

import hashlib
from lab_generate_skill.domain.preparation_record import (
    PreparationInputs,
    PreparationSelection,
    PreparedPublication,
    PreparationRecordFailure,
)
from lab_generate_skill.domain.preparation import PreparationReceipt, PreparedTask
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.preparation_records import (
    PreparationChecks,
    PreparationBodyChecks,
    PreparationAuthority,
    PreparationInputReads,
    LoadedPreparedTask,
)
from lab_generate_skill.domain.preparation_read import PreparationReadRequest
from lab_generate_skill.ports.preparation_record_inputs import (
    LoadedPreparation,
    PreparationRecordInputReads,
    PreparationCheckInputReads,
)
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.adapters.plans.preparation_evidence import (
    PreparationEvidenceReader,
)


class EvidencePreparationRecords:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        bindings: TaskBindings,
        checks: PreparationChecks,
        authority: PreparationAuthority,
        *,
        input_reads: PreparationInputReads | None = None,
        record_inputs: PreparationRecordInputReads | None = None,
    ) -> None:
        self.store, self.controls, self.checks, self.authority = (
            store,
            controls,
            checks,
            authority,
        )
        self.reader = PreparationEvidenceReader(store, bindings)
        self.input_reads = input_reads
        self.record_inputs = record_inputs

    def _read_inputs(
        self,
        selection: PreparationSelection,
        op: OperationContext,
        control: OperationControl,
    ) -> LoadedPreparation:
        request = PreparationReadRequest(selection=selection, operation=op)
        bodies = (
            None
            if self.input_reads is None
            else self.input_reads.load_preparation_inputs(request, control)
        )
        if bodies is None:
            loaded = self.reader.load_with_bodies(selection, op, control)
        else:
            if bodies.request != request:
                raise OwnershipConflict("Preparation proof changed original read")
            loaded = LoadedPreparation(
                bodies.inputs,
                frozenset(bodies.verified),
                bodies.private_spec_json.encode(),
                bodies.snapshot_json.encode(),
            )
        return loaded

    def _verify(
        self,
        selection: PreparationSelection,
        op: OperationContext,
        control: OperationControl,
    ) -> tuple[PreparationInputs, PreparationReceipt]:
        loaded = (
            self._read_inputs(selection, op, control)
            if self.record_inputs is None
            else self.record_inputs.preparation_inputs(
                selection,
                op,
                control,
                lambda: self._read_inputs(selection, op, control),
            )
        )
        inputs = loaded.inputs
        original = inputs.request.operation
        if op != original and not (
            op.mode == "cleanup"
            and op.parent_operation_id == original.operation_id
            and (
                op.run_id,
                op.owner_id,
                op.attempt_id,
                op.allocation_id,
                op.recovery_ref,
            )
            == (
                original.run_id,
                original.owner_id,
                original.attempt_id,
                original.allocation_id,
                original.recovery_ref,
            )
        ):
            raise OwnershipConflict(
                "Preparation records need original operation or its cleanup"
            )

        def check() -> StateChecks:
            return StateChecks.model_validate(
                self.checks.check_with_bodies(
                    inputs, loaded.private_spec, loaded.snapshot, control
                )
                if isinstance(self.checks, PreparationBodyChecks)
                else self.checks.check(inputs, control)
            )

        checks = (
            self.record_inputs.preparation_checks(
                inputs, self.checks, op, control, check
            )
            if isinstance(self.record_inputs, PreparationCheckInputReads)
            else check()
        )
        if checks.required != inputs.spec.preparation_checks:
            raise OwnershipConflict("Preparation cannot narrow frozen coverage")
        for reference in dict.fromkeys(evidence_references(checks)):
            control.checkpoint()
            if reference not in loaded.verified:
                self.reader.reads.read(reference, control)
        self.authority.verify(inputs, checks, op, control)
        control.checkpoint()
        assert original.recovery_ref is not None
        receipt = PreparationReceipt(
            scope=inputs.environment.scope,
            operation=original,
            task_binding_ref=inputs.request.binding_ref,
            spec_ref=inputs.binding.baseline_ref,
            environment_ref=selection.environment_ref,
            recovery_ref=original.recovery_ref,
            checks=checks,
        )
        return inputs, receipt

    def _prepared(
        self, inputs: PreparationInputs, reference: EvidenceRef
    ) -> PreparedTask:
        assert inputs.request.operation.recovery_ref is not None
        return PreparedTask(
            scope=inputs.environment.scope,
            public_task=inputs.public_task,
            task_binding_ref=inputs.request.binding_ref,
            spec_ref=inputs.binding.baseline_ref,
            preparation_ref=reference,
            private_checks_ref=inputs.binding.private_spec_ref,
            recovery_ref=inputs.request.operation.recovery_ref,
        )

    def _put(
        self,
        item: PreparationReceipt | PreparedTask,
        control: OperationControl,
        candidates: list[EvidenceRef],
    ) -> EvidenceRef:
        control.checkpoint()
        raw = item.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=item.schema_version,
            visibility="private",
            producer="preparation-records-v1",
        )
        ref = EvidenceRef.model_validate(self.store.put(raw, metadata, control=control))
        candidates.append(ref)
        if (
            ref.sha256,
            ref.size_bytes,
            ref.media_type,
            ref.content_schema,
            ref.visibility,
            ref.producer,
        ) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            metadata.media_type,
            metadata.content_schema,
            metadata.visibility,
            metadata.producer,
        ):
            raise EvidenceIntegrityError(
                "Store changed original preparation publication"
            )
        control.checkpoint()
        return ref

    def publish(
        self, selection: PreparationSelection, op: OperationContext
    ) -> PreparedPublication:
        selection = PreparationSelection.model_validate(selection)
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        candidates: list[EvidenceRef] = []
        phase = "verify"
        try:
            control.checkpoint()
            inputs, receipt = self._verify(selection, op, control)
            phase = "preparation"
            ref = self._put(receipt, control, candidates)
            phase = "prepared"
            prepared_ref = self._put(self._prepared(inputs, ref), control, candidates)
            return PreparedPublication(
                selection=selection, preparation_ref=ref, prepared_ref=prepared_ref
            )
        except Exception as error:
            raise PreparationRecordFailure(phase, error, tuple(candidates)) from error

    def load(
        self, publication: PreparedPublication, op: OperationContext
    ) -> PreparedTask:
        return self.load_with_receipt(publication, op).prepared

    def load_with_receipt(
        self, publication: PreparedPublication, op: OperationContext
    ) -> LoadedPreparedTask:
        publication = PreparedPublication.model_validate(publication)
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        control.checkpoint()
        inputs, expected = self._verify(publication.selection, op, control)
        private_state_ref(publication.preparation_ref, "preparation-receipt/1")
        private_state_ref(publication.prepared_ref, "prepared-task/1")

        def read() -> tuple[bytes, bytes]:
            return (
                self.reader.reads.read(publication.preparation_ref, control),
                self.reader.reads.read(publication.prepared_ref, control),
            )

        raw = (
            read()
            if self.record_inputs is None
            else self.record_inputs.publication_inputs(publication, op, control, read)
        )
        receipt = PreparationReceipt.model_validate_json(raw[0])
        prepared = PreparedTask.model_validate_json(raw[1])
        if receipt != expected or prepared != self._prepared(
            inputs, publication.preparation_ref
        ):
            raise OwnershipConflict(
                "Prepared publication differs from actual original facts"
            )
        control.checkpoint()
        return LoadedPreparedTask(prepared, receipt, inputs)
