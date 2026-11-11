"""Actual reset graph: full original closures/recovery and no physical actions."""

from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.reset_publication import (
    require_reset_bodies,
    reset_documents,
)
from lab_generate_skill.domain.lifecycle import RecoveryPlan, ClosureReceipt
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    ResetReceipt,
    TaskResetReceipt,
    EnvironmentResetReceipt,
    ResetHealthReceipt,
    assemble_reset,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


class ResetEvidenceReader:
    def __init__(self, store: EvidenceReader) -> None:
        self.reads = StateReads(store)

    def verify(
        self,
        receipt: ResetReceipt,
        control: OperationControl,
        *,
        inputs: ResetInputs | None = None,
    ) -> ResetInputs:
        receipt = ResetReceipt.model_validate(receipt)
        if inputs is not None:
            inputs = ResetInputs.model_validate(inputs)
            control.checkpoint()
            require_reset_bodies(receipt, inputs)
            # Only bodies supplied by this synchronous producer are reused.
            # Every other complete dependency still undergoes the original read.
            verified = {reference for reference, _ in reset_documents(inputs)}
            recoveries = {
                inputs.plan.task_recovery_ref: inputs.task_recovery,
                inputs.plan.environment_recovery_ref: inputs.environment_recovery,
            }
            for closure in inputs.closures:
                reference = closure.token.recovery_ref
                recovery = recoveries.get(reference)
                if recovery is None:
                    recovery = self.reads.parse(
                        reference, "recovery-plan/1", RecoveryPlan, control
                    )
                    recoveries[reference] = recovery
                    verified.add(reference)
                if (
                    recovery.owner != closure.token.owner
                    or recovery.attempt_id != closure.token.attempt_id
                ):
                    raise OwnershipConflict(
                        "Closed resource recovery belongs to another original owner/attempt"
                    )
            # Parse every distinct resource-specific recovery before the one
            # dependency pass. It may differ from both plan-level recoveries.
            for dependency in dict.fromkeys(
                evidence_references((inputs, *recoveries.values()))
            ):
                if dependency not in verified:
                    self.reads.read(dependency, control)
                    verified.add(dependency)
            control.checkpoint()
            return inputs
        read = self.reads.parse
        plan = read(receipt.plan_ref, "reset-plan/1", ResetPlan, control)
        spec = read(plan.spec_ref, "initial-state-spec/1", InitialStateSpec, control)
        task_recovery = read(
            plan.task_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        environment_recovery = read(
            plan.environment_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        closures = tuple(
            read(ref, "closure-receipt/1", ClosureReceipt, control)
            for ref in receipt.closure_refs
        )
        task = read(receipt.task_reset_ref, "task-reset/1", TaskResetReceipt, control)
        environment = read(
            receipt.environment_reset_ref,
            "environment-reset/1",
            EnvironmentResetReceipt,
            control,
        )
        health = read(receipt.health_ref, "reset-health/1", ResetHealthReceipt, control)
        inputs = ResetInputs(
            plan=plan,
            plan_ref=receipt.plan_ref,
            spec=spec,
            task_recovery=task_recovery,
            environment_recovery=environment_recovery,
            closures=closures,
            closure_refs=receipt.closure_refs,
            task=task,
            task_ref=receipt.task_reset_ref,
            environment=environment,
            environment_ref=receipt.environment_reset_ref,
            health=health,
            health_ref=receipt.health_ref,
        )
        if assemble_reset(inputs, receipt.operation) != receipt:
            raise OwnershipConflict("Reset summary differs from actual cleanup facts")
        self.reads.dependencies((inputs,), control)
        for closure in closures:
            recovery = read(
                closure.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
            )
            if (
                recovery.owner != closure.token.owner
                or recovery.attempt_id != closure.token.attempt_id
            ):
                raise OwnershipConflict(
                    "Closed resource recovery belongs to another original owner/attempt"
                )
            self.reads.dependencies((recovery,), control)
        control.checkpoint()
        return inputs
