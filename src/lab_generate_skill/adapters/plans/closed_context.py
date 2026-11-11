"""Recheck one closed source through its original readers, never grant new work."""

from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
)
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.state_qualification import StateQualificationChecks


class ClosedSourceContextAuthority:
    def __init__(
        self,
        source: PublicContextReceipt,
        *,
        environment: EnvironmentSelection,
        environment_ref: EvidenceRef,
        restoration: ResetSelection,
        restoration_ref: EvidenceRef,
        initial: InitialObservationSelection,
        browser_closure: ClosureReceipt,
        state_checks: StateQualificationChecks,
        initial_checks: InitialObservationChecks,
        preparations: PreparationRecords,
        evidence: EvidenceReader,
        controls: OperationControls,
    ) -> None:
        self.source = PublicContextReceipt.model_validate(source)
        self.environment = EnvironmentSelection.model_validate(environment)
        self.restoration = ResetSelection.model_validate(restoration)
        self.initial = InitialObservationSelection.model_validate(initial)
        self.environment_ref, self.restoration_ref = environment_ref, restoration_ref
        self.browser_closure = ClosureReceipt.model_validate(browser_closure)
        self.states, self.initial_checks, self.controls = (
            state_checks,
            initial_checks,
            controls,
        )
        self.initial_reader = InitialObservationReader(evidence, preparations)
        if (
            self.environment.scope != self.source.scope
            or self.restoration.environment_selection_ref != environment_ref
            or self.browser_closure.token.owner != self.source.scope.owner
            or self.browser_closure.token.attempt_id != self.source.scope.attempt_id
            or self.browser_closure.status != "closed"
        ):
            raise OwnershipConflict("Closed source changed its original scope/closure")

    def _guard(self, operation: OperationContext) -> None:
        if (operation.run_id, operation.owner_id) != (
            self.source.scope.owner.run_id,
            self.source.scope.owner.owner_id,
        ):
            raise OwnershipConflict("Closed source read changed original run/owner")
        self.controls.bind(operation).checkpoint()

    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        self._guard(op)
        control = self.controls.bind(op)
        if receipt.scope != self.source.scope or receipt.status != "ready":
            raise OwnershipConflict("Closed source baseline changed its original scope")
        actual_environment = self.states.environment(
            self.environment,
            self.environment_ref,
            inputs.environment.operation,
            control,
        )
        original = read_operation(inputs.preparation.operation, op)
        initial = self.initial_reader.load(self.initial, original, control)
        checked = self.initial_checks.check(initial, control)
        if (
            inputs.environment != actual_environment
            or inputs.prepared != initial.prepared
            or inputs.spec != initial.spec
            or inputs.initial.checks != checked
            or inputs.observation != initial.observation.record
            or inputs.observation.sequence != 0
            or inputs.observation_ref != receipt.observation_ref
            or inputs.spec_ref != self.source.spec_ref
        ):
            raise OwnershipConflict(
                "Closed source initial facts differ from original measurements"
            )
        control.checkpoint()

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        self._guard(op)
        control = self.controls.bind(op)
        checked = self.states.reset(self.restoration, self.restoration_ref, control)
        if (
            receipt.scope != self.source.scope
            or receipt.status != "safe"
            or (
                inputs.plan,
                inputs.spec,
                inputs.closures,
                inputs.task.checks,
                inputs.environment.checks,
                inputs.health.checks,
            )
            != (
                checked.plan,
                checked.spec,
                checked.closures,
                checked.task,
                checked.environment,
                checked.health,
            )
            or inputs.closures != (self.browser_closure,)
        ):
            raise OwnershipConflict(
                "Closed source reset differs from original restore/resume/closure"
            )
        control.checkpoint()

    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None:
        self._guard(op)
        if receipt != self.source or (
            inputs.baseline_ref,
            inputs.reset_ref,
            inputs.context_ref,
            inputs.context.initial_observation_ref,
        ) != (
            self.source.baseline_ref,
            self.source.reset_ref,
            self.source.public_context_ref,
            inputs.baseline.observation_ref,
        ):
            raise OwnershipConflict(
                "Closed source context changed its original immutable projection"
            )

    def verify_equivalence(
        self,
        inputs: EquivalenceInputs,
        receipt: EquivalenceReceipt,
        op: OperationContext,
    ) -> None:
        raise OwnershipConflict(
            "Closed source reads cannot grant candidate equivalence"
        )
