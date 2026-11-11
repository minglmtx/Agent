"""Resolve actual source/candidate graphs and mandatory historical authority.

Reuse the same baseline/reset readers and StateAuthority contract as StateRecords.
This aggregate may read an authorized frozen source from another attempt, without
rebinding the caller operation or weakening StateRecords' attempt-level boundary.
"""

from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceChecks,
    EquivalenceInputs,
    EquivalenceReceipt,
    assemble_equivalence,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from lab_generate_skill.domain.reset import ResetReceipt
from lab_generate_skill.ports.contexts import ContextAuthority, ContextInputReads
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.state_records import BaselineInputReads
from lab_generate_skill.ports.initial_adoption import InitialAdoptionAuthority
from lab_generate_skill.policies.equivalence_inputs import checked_equivalence_bodies
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes


class ContextEvidenceReader:
    def __init__(
        self,
        store: EvidenceReader,
        authority: ContextAuthority,
        *,
        input_reads: ContextInputReads | None = None,
        baseline_input_reads: BaselineInputReads | None = None,
        adoption_checks: InitialAdoptionAuthority | None = None,
    ) -> None:
        self.reads = StateReads(store)
        self.baselines = BaselineEvidenceReader(store, input_reads=baseline_input_reads)
        self.resets = ResetEvidenceReader(store)
        self.authority = authority
        self.input_reads = input_reads
        if adoption_checks is not None and not isinstance(
            adoption_checks, InitialAdoptionAuthority
        ):
            raise TypeError("Explicit current initial-adoption authority required")
        self.adoption_checks = adoption_checks

    def verify_adoption(
        self,
        inputs: InitialAdoptionInputs | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if inputs is None:
            if self.adoption_checks is not None:
                raise OwnershipConflict(
                    "Selected adoption reader cannot downgrade to ordinary comparison"
                )
            return
        if self.adoption_checks is None or inputs != self.adoption_checks.inputs:
            raise OwnershipConflict(
                "Initial adoption requires its exact live selected authority"
            )
        self.adoption_checks.verify_adoption(inputs, operation, control)
        control.checkpoint()

    def verify_equivalence_inputs(
        self,
        inputs: EquivalenceInputs,
        receipt: EquivalenceReceipt,
        op: OperationContext,
        control: OperationControl,
        *,
        dependencies: dict[EvidenceRef, bytes] | None = None,
    ) -> dict[EvidenceRef, bytes]:
        inputs = EquivalenceInputs.model_validate(inputs)
        receipt = EquivalenceReceipt.model_validate(receipt)
        op = OperationContext.model_validate(op)
        if (op.run_id, op.owner_id) != (
            receipt.scope.owner.run_id,
            receipt.scope.owner.owner_id,
        ):
            raise OwnershipConflict("Equivalence input read changed original caller")
        control.checkpoint()
        self.verify_adoption(inputs.adoption, op, control)
        bodies = checked_equivalence_bodies(inputs, receipt)
        refs = tuple(dict.fromkeys(evidence_references((inputs.checks,))))
        if dependencies is not None and set(dependencies) != set(refs):
            raise OwnershipConflict(
                "Equivalence dependency handoff changed complete reference set"
            )
        checked: dict[EvidenceRef, bytes] = {}
        # Same immutable bodies, original current authority. The concrete owned
        # authority reads the complete closed source and actual measurements;
        # it also recomputes the declared comparison and checks current claim.
        source_read = (
            None
            if self.input_reads is None
            else self.input_reads.read_inputs(inputs.source, op, control)
        )
        try:
            if source_read is not None and source_read.inputs != inputs.source_inputs:
                raise OwnershipConflict(
                    "Source handoff changed original complete inputs"
                )
            source_checks = self.authority if source_read is None else source_read
            source_checks.verify_baseline(
                inputs.source_inputs.baseline_inputs, inputs.source_inputs.baseline, op
            )
            control.checkpoint()
            source_checks.verify_reset(
                inputs.source_inputs.reset_inputs, inputs.source_inputs.reset, op
            )
            control.checkpoint()
            source_checks.verify_context(inputs.source_inputs, inputs.source, op)
            control.checkpoint()
        finally:
            if source_read is not None:
                source_read.close()
        self.authority.verify_baseline(inputs.candidate_inputs, inputs.candidate, op)
        for ref in refs:
            control.checkpoint()
            raw = bodies.get(ref)
            if raw is None:
                raw = (
                    self.reads.read(ref, control)
                    if dependencies is None
                    else dependencies[ref]
                )
            require_complete_bytes(ref, raw)
            if dependencies is not None and dependencies[ref] != raw:
                raise OwnershipConflict(
                    "Equivalence dependency changed current producer body"
                )
            checked[ref] = raw
        self.authority.verify_equivalence(inputs, receipt, op)
        self.verify_adoption(inputs.adoption, op, control)
        control.checkpoint()
        return checked

    def context(
        self,
        receipt: PublicContextReceipt,
        op: OperationContext,
        control: OperationControl,
        *,
        adoption: InitialAdoptionInputs | None = None,
    ) -> PublicContextInputs:
        receipt = PublicContextReceipt.model_validate(receipt)
        if adoption is None and (op.run_id, op.owner_id) != (
            receipt.scope.owner.run_id,
            receipt.scope.owner.owner_id,
        ):
            raise OwnershipConflict("Frozen source belongs to another run/owner")
        control.checkpoint()
        self.verify_adoption(adoption, op, control)
        loaded = (
            None
            if self.input_reads is None
            else self.input_reads.read_inputs(receipt, op, control)
        )
        try:
            if loaded is None:
                read = self.reads.parse
                public = read(
                    receipt.public_context_ref,
                    "public-construction-context/1",
                    PublicConstructionContext,
                    control,
                    visibility="public",
                )
                baseline = read(
                    receipt.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
                )
                reset = read(
                    receipt.reset_ref, "reset-receipt/1", ResetReceipt, control
                )
                initial = self.baselines.verify(baseline, control, operation=op)
                restoration = self.resets.verify(reset, control)
                inputs = PublicContextInputs(
                    context=public,
                    context_ref=receipt.public_context_ref,
                    baseline_inputs=initial,
                    baseline=baseline,
                    baseline_ref=receipt.baseline_ref,
                    reset_inputs=restoration,
                    reset=reset,
                    reset_ref=receipt.reset_ref,
                )
            else:
                inputs = PublicContextInputs.model_validate(loaded.inputs)
                if (inputs.context_ref, inputs.baseline_ref, inputs.reset_ref) != (
                    receipt.public_context_ref,
                    receipt.baseline_ref,
                    receipt.reset_ref,
                ):
                    raise OwnershipConflict(
                        "Context input proof changed exact source references"
                    )
            control.checkpoint()
            if assemble_public_context(inputs, receipt.operation) != receipt:
                raise OwnershipConflict(
                    "Frozen context differs from actual source facts"
                )
            if adoption is not None:
                adoption.require_source(
                    adoption.binding.source_context_ref, receipt, inputs
                )
            checks = self.authority if loaded is None else loaded
            checks.verify_baseline(inputs.baseline_inputs, inputs.baseline, op)
            control.checkpoint()
            checks.verify_reset(inputs.reset_inputs, inputs.reset, op)
            control.checkpoint()
            checks.verify_context(inputs, receipt, op)
            self.verify_adoption(adoption, op, control)
            control.checkpoint()
            return inputs
        finally:
            if loaded is not None:
                loaded.close()

    def equivalence(
        self,
        receipt: EquivalenceReceipt,
        op: OperationContext,
        control: OperationControl,
    ) -> EquivalenceInputs:
        receipt = EquivalenceReceipt.model_validate(receipt)
        if (op.run_id, op.owner_id) != (
            receipt.scope.owner.run_id,
            receipt.scope.owner.owner_id,
        ):
            raise OwnershipConflict("Candidate comparison belongs to another run/owner")
        read = self.reads.parse
        source = read(
            receipt.source_context_receipt_ref,
            "public-context-receipt/1",
            PublicContextReceipt,
            control,
        )
        adoption = None
        if receipt.adoption is not None:
            current = read(
                receipt.adoption.execution_source_ref,
                "execution-task-source/2",
                ExecutionTaskSource,
                control,
            )
            adoption = InitialAdoptionInputs(binding=receipt.adoption, source=current)
        self.verify_adoption(adoption, op, control)
        source_inputs = self.context(source, op, control, adoption=adoption)
        candidate = read(
            receipt.candidate_baseline_ref,
            "baseline-receipt/1",
            BaselineReceipt,
            control,
        )
        candidate_inputs = self.baselines.verify(candidate, control, operation=op)
        facts = read(
            receipt.checks_ref,
            receipt.checks_ref.content_schema,
            EquivalenceChecks,
            control,
        )
        if facts.schema_version != receipt.checks_ref.content_schema:
            raise OwnershipConflict("Comparison body changed its exact selected schema")
        self.reads.dependencies((facts,), control)
        inputs = EquivalenceInputs(
            source_inputs=source_inputs,
            source=source,
            source_ref=receipt.source_context_receipt_ref,
            candidate_inputs=candidate_inputs,
            candidate=candidate,
            candidate_ref=receipt.candidate_baseline_ref,
            checks=facts,
            checks_ref=receipt.checks_ref,
            adoption=adoption,
        )
        if assemble_equivalence(inputs, receipt.operation) != receipt:
            raise OwnershipConflict(
                "Equivalence summary differs from actual comparison facts"
            )
        self.authority.verify_baseline(candidate_inputs, candidate, op)
        control.checkpoint()
        self.authority.verify_equivalence(inputs, receipt, op)
        self.verify_adoption(adoption, op, control)
        control.checkpoint()
        return inputs
