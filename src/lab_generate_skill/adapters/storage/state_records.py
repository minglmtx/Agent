"""State-summary CAS publication/consumption; no environment or recovery actions.

Historical receipt operations are never rewritten. A fresh bounded cleanup
operation may reconcile the exact summary, linked to its original operation.
"""

from dataclasses import dataclass
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.baseline import BaselineReceipt, assemble_baseline
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt, assemble_reset
from lab_generate_skill.domain.reset_publication import (
    PublishedReset,
    require_reset_bodies,
)
from lab_generate_skill.domain.state_scope import StateFact, StateCommitUnconfirmed
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.state_records import (
    StateAuthority,
    BaselineInputReads,
    ResetInputAuthority,
)
from lab_generate_skill.domain.baseline import BaselineInputs


@dataclass(frozen=True)
class _ResetPublicationIdentity:
    adapter: object
    reference: EvidenceRef
    receipt: ResetReceipt
    inputs: ResetInputs


class EvidenceStateRecords:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        authority: StateAuthority,
        *,
        input_reads: BaselineInputReads | None = None,
    ) -> None:
        self.store, self.controls, self.authority = store, controls, authority
        self.baselines = BaselineEvidenceReader(store, input_reads=input_reads)
        self.resets = ResetEvidenceReader(store)
        self.reads = StateReads(store)
        self._reset_publication_issuer = object()

    def _guard(
        self, receipt: StateFact, op: OperationContext, *, writing: bool
    ) -> OperationControl:
        owner = receipt.scope.owner
        if (op.run_id, op.owner_id) != (owner.run_id, owner.owner_id) or (
            op.attempt_id is not None and op.attempt_id != receipt.scope.attempt_id
        ):
            raise OwnershipConflict("State transport cannot change run/owner/attempt")
        if writing:
            if op.attempt_id != receipt.scope.attempt_id:
                raise OwnershipConflict("State publication requires its attempt")
            if op != receipt.operation and not (
                op.mode == "cleanup"
                and op.parent_operation_id == receipt.operation.operation_id
                and (op.allocation_id, op.recovery_ref)
                == (receipt.operation.allocation_id, receipt.operation.recovery_ref)
            ):
                raise OwnershipConflict(
                    "Publication must use original operation or its bounded cleanup reconciliation"
                )
        control = self.controls.bind(op)
        control.checkpoint()
        return control

    def _put(
        self, receipt: BaselineReceipt | ResetReceipt, control: OperationControl
    ) -> EvidenceRef:
        control.checkpoint()
        raw = receipt.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=receipt.schema_version,
            visibility="private",
            producer="state-records-v1",
        )
        candidate = evidence_reference(raw, metadata)
        try:
            reference = self.store.put(raw, metadata, control=control)
        except BaseException as error:
            # A candidate can be checked read-only; it is not a confirmed save
            # or permission to repeat native restore/resume/publication.
            setattr(error, "state_candidate_reference", candidate)
            raise
        try:
            control.checkpoint()
        except Exception as error:
            raise StateCommitUnconfirmed(reference) from error
        return reference

    def publish_baseline(
        self, receipt: BaselineReceipt, op: OperationContext
    ) -> EvidenceRef:
        receipt = BaselineReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        inputs = self.baselines.verify(receipt, control, operation=op)
        self.authority.verify_baseline(inputs, receipt, op)
        return self._put(receipt, control)

    def publish_baseline_verified(
        self, receipt: BaselineReceipt, op: OperationContext
    ) -> EvidenceRef:
        """One graph proof across publication and exact readback, no cached grant."""
        receipt = BaselineReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        inputs: BaselineInputs = self.baselines.verify(receipt, control, operation=op)
        self.authority.verify_baseline(inputs, receipt, op)
        reference = self._put(receipt, control)
        try:
            actual = self.reads.parse(
                reference, "baseline-receipt/1", BaselineReceipt, control
            )
            if (
                actual != receipt
                or assemble_baseline(inputs, actual.operation) != actual
            ):
                raise OwnershipConflict(
                    "Published baseline readback changed original receipt"
                )
            self._guard(actual, op, writing=False)
            # The original consumption authority is still called anew. Only
            # immutable bodies from this synchronous proof are handed onward.
            self.authority.verify_baseline(inputs, actual, op)
            control.checkpoint()
            return reference
        except BaseException as error:
            raise StateCommitUnconfirmed(reference) from error

    def load_baseline(
        self, reference: EvidenceRef, op: OperationContext
    ) -> BaselineReceipt:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        receipt = self.reads.parse(
            reference, "baseline-receipt/1", BaselineReceipt, control
        )
        self._guard(receipt, op, writing=False)
        inputs = self.baselines.verify(receipt, control, operation=op)
        self.authority.verify_baseline(inputs, receipt, op)
        control.checkpoint()
        return receipt

    def publish_reset(self, receipt: ResetReceipt, op: OperationContext) -> EvidenceRef:
        receipt = ResetReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        inputs = self.resets.verify(receipt, control)
        self.authority.verify_reset(inputs, receipt, op)
        return self._put(receipt, control)

    def publish_reset_verified(
        self, receipt: ResetReceipt, op: OperationContext
    ) -> EvidenceRef:
        """One synchronous complete graph, exact readback and two fresh authorities."""
        receipt = ResetReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        inputs = self.resets.verify(receipt, control)
        self.authority.verify_reset(inputs, receipt, op)
        reference = self._put(receipt, control)
        try:
            actual = self.reads.parse(
                reference, "reset-receipt/1", ResetReceipt, control
            )
            if actual != receipt or assemble_reset(inputs, actual.operation) != actual:
                raise OwnershipConflict(
                    "Published reset readback changed original receipt"
                )
            self._guard(actual, op, writing=False)
            self.authority.verify_reset(inputs, actual, op)
            control.checkpoint()
            return reference
        except BaseException as error:
            raise StateCommitUnconfirmed(reference) from error

    def load_reset(self, reference: EvidenceRef, op: OperationContext) -> ResetReceipt:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        receipt = self.reads.parse(reference, "reset-receipt/1", ResetReceipt, control)
        self._guard(receipt, op, writing=False)
        inputs = self.resets.verify(receipt, control)
        self.authority.verify_reset(inputs, receipt, op)
        control.checkpoint()
        return receipt

    def publish_reset_inputs(
        self, receipt: ResetReceipt, inputs: ResetInputs, op: OperationContext
    ) -> PublishedReset:
        """Consume complete producer bodies once, publish/read back, recheck authority."""
        receipt = ResetReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        control = self._guard(receipt, op, writing=True)
        inputs = self.resets.verify(receipt, control, inputs=inputs)
        self._verify_reset_inputs(inputs, receipt, op)
        reference = self._put(receipt, control)
        try:
            actual = self.reads.parse(
                reference, "reset-receipt/1", ResetReceipt, control
            )
            if actual != receipt:
                raise OwnershipConflict(
                    "Published Reset readback changed original receipt"
                )
            self._guard(actual, op, writing=False)
            self._verify_reset_inputs(inputs, actual, op)
            control.checkpoint()
            identity = _ResetPublicationIdentity(
                self._reset_publication_issuer, reference, actual, inputs
            )
            return PublishedReset(reference, actual, inputs, identity)
        except BaseException as error:
            raise StateCommitUnconfirmed(reference) from error

    def load_reset_publication(
        self, publication: PublishedReset, op: OperationContext
    ) -> ResetReceipt:
        if not isinstance(publication, PublishedReset):
            raise OwnershipConflict(
                "Reset handoff requires its original typed publication"
            )
        identity = publication.issuer
        if (
            not isinstance(identity, _ResetPublicationIdentity)
            or identity.adapter is not self._reset_publication_issuer
            or identity.reference != publication.reference
            or identity.receipt is not publication.receipt
            or identity.inputs is not publication.inputs
        ):
            raise OwnershipConflict(
                "Reset handoff must come from this original publication consumer"
            )
        receipt, inputs = publication.receipt, publication.inputs
        require_reset_bodies(receipt, inputs)
        control = self._guard(
            receipt, OperationContext.model_validate(op), writing=False
        )
        self._verify_reset_inputs(inputs, receipt, op)
        control.checkpoint()
        return receipt

    def _verify_reset_inputs(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        if isinstance(self.authority, ResetInputAuthority):
            self.authority.verify_reset_inputs(inputs, receipt, op)
        else:
            self.authority.verify_reset(inputs, receipt, op)
