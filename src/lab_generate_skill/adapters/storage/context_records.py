"""Qualification CAS transport, without performing capture/compare/reset actions.

Original receipt operations remain unchanged. Post-commit failure carries the
known reference; expired operations may reconcile via an independent bounded
cleanup command with the exact original parent and resource scope.
"""

from lab_generate_skill.adapters.plans.context_evidence import ContextEvidenceReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceReceipt,
    EquivalenceInputs,
    private_equivalence_ref,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextReceipt,
    PublicContextInputs,
    ContextCommitUnconfirmed,
)
from lab_generate_skill.ports.contexts import ContextAuthority, ContextInputReads
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.state_records import BaselineInputReads
from lab_generate_skill.ports.initial_adoption import InitialAdoptionAuthority


class EvidenceContextRecords:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        authority: ContextAuthority,
        *,
        input_reads: ContextInputReads | None = None,
        baseline_input_reads: BaselineInputReads | None = None,
        adoption_checks: InitialAdoptionAuthority | None = None,
    ) -> None:
        self.store, self.controls = store, controls
        self.facts = ContextEvidenceReader(
            store,
            authority,
            input_reads=input_reads,
            baseline_input_reads=baseline_input_reads,
            adoption_checks=adoption_checks,
        )
        self.reads = StateReads(store)

    def _guard(
        self,
        receipt: PublicContextReceipt | EquivalenceReceipt,
        op: OperationContext,
        *,
        writing: bool,
    ) -> OperationControl:
        owner = receipt.scope.owner
        if (op.run_id, op.owner_id) != (owner.run_id, owner.owner_id):
            raise OwnershipConflict("Qualification cannot change its run/owner")
        if isinstance(receipt, EquivalenceReceipt) and op.attempt_id not in (
            None,
            receipt.scope.attempt_id,
        ):
            raise OwnershipConflict(
                "Equivalence belongs to a different candidate attempt"
            )
        original = receipt.operation
        if writing and (
            op.attempt_id != original.attempt_id
            or (
                op != original
                and not (
                    op.mode == "cleanup"
                    and op.parent_operation_id == original.operation_id
                    and (op.allocation_id, op.recovery_ref)
                    == (original.allocation_id, original.recovery_ref)
                )
            )
        ):
            raise OwnershipConflict(
                "Publication needs its original operation or exact cleanup reconciliation"
            )
        control = self.controls.bind(op)
        control.checkpoint()
        return control

    def _put(
        self,
        receipt: PublicContextReceipt | EquivalenceReceipt,
        control: OperationControl,
    ) -> EvidenceRef:
        control.checkpoint()
        reference = self.store.put(
            receipt.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=receipt.schema_version,
                visibility="private",
                producer="context-records-v1",
            ),
            control=control,
        )
        try:
            control.checkpoint()
        except Exception as error:
            raise ContextCommitUnconfirmed(reference) from error
        return reference

    def publish_context(
        self, receipt: PublicContextReceipt, op: OperationContext
    ) -> EvidenceRef:
        receipt = PublicContextReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        self.facts.context(receipt, op, control)
        return self._put(receipt, control)

    def load_context(
        self, reference: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt:
        return self.load_context_inputs(reference, op)[0]

    def load_context_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> tuple[PublicContextReceipt, PublicContextInputs]:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        receipt = self.reads.parse(
            reference, "public-context-receipt/1", PublicContextReceipt, control
        )
        selected = self.facts.adoption_checks
        if (
            selected is not None
            and reference == selected.inputs.binding.source_context_ref
        ):
            return receipt, self.facts.context(
                receipt, op, control, adoption=selected.inputs
            )
        self._guard(receipt, op, writing=False)
        return receipt, self.facts.context(receipt, op, control)

    def publish_equivalence(
        self, receipt: EquivalenceReceipt, op: OperationContext
    ) -> EvidenceRef:
        receipt = EquivalenceReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        self.facts.equivalence(receipt, op, control)
        return self._put(receipt, control)

    def publish_equivalence_verified(
        self,
        receipt: EquivalenceReceipt,
        inputs: EquivalenceInputs,
        op: OperationContext,
    ) -> EvidenceRef:
        return self.publish_equivalence_inputs(receipt, inputs, op)[0]

    def publish_equivalence_inputs(
        self,
        receipt: EquivalenceReceipt,
        inputs: EquivalenceInputs,
        op: OperationContext,
    ) -> tuple[EvidenceRef, dict[EvidenceRef, bytes]]:
        """Consume this producer's full inputs, publish and verify exact readback.

        No source permission or graph is cached across calls. Historical readers
        retain their complete graph path; this explicit producer handoff keeps
        the original current semantic authorities on both sides of publication.
        """
        receipt = EquivalenceReceipt.model_validate(receipt)
        inputs = EquivalenceInputs.model_validate(inputs)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        dependencies = self.facts.verify_equivalence_inputs(
            inputs, receipt, op, control
        )
        reference = self._put(receipt, control)
        try:
            expected = evidence_reference(
                receipt.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema=receipt.schema_version,
                    visibility="private",
                    producer="context-records-v1",
                ),
            )
            actual = self.reads.parse(
                reference, receipt.schema_version, EquivalenceReceipt, control
            )
            if reference != expected or actual != receipt:
                raise OwnershipConflict(
                    "Equivalence publication/readback changed original reference or body"
                )
            self._guard(actual, op, writing=False)
            self.facts.verify_equivalence_inputs(
                inputs, actual, op, control, dependencies=dependencies
            )
            control.checkpoint()
            return reference, dependencies
        except BaseException as error:
            raise ContextCommitUnconfirmed(reference) from error

    def load_equivalence(
        self, reference: EvidenceRef, op: OperationContext
    ) -> EquivalenceReceipt:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        private_equivalence_ref(reference)
        receipt = self.reads.parse(
            reference, reference.content_schema, EquivalenceReceipt, control
        )
        if receipt.schema_version != reference.content_schema:
            raise OwnershipConflict(
                "Equivalence body changed its exact selected schema"
            )
        self._guard(receipt, op, writing=False)
        self.facts.equivalence(receipt, op, control)
        return receipt
