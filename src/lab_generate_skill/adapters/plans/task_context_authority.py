"""Original source plus measured candidate state; no invented initial equivalence.

The source is re-read through its closed-resource authority. Candidate facts must
come from the retained current initializer and original measured state/checks.
Historical validation grants no live Actor/model/browser permission.
"""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
)
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    assemble_public_context,
    PublicContextReceipt,
)
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.ports.contexts import (
    ContextRecords,
    ContextFactReads,
    ContextInputRead,
)
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.state_qualification import StateQualificationChecks
from lab_generate_skill.ports.task_initialization import (
    TaskInitialComparison,
    TaskAdoptedInitialComparison,
    TaskInitialComparisonReads,
)
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)
from lab_generate_skill.ports.state_records import BaselineInputReads


class OriginalTaskContextAuthority:
    def __init__(
        self,
        resources: OriginalTaskResourceOwner,
        preparation: RecordedSiteTaskPreparation,
        initialization: Callable[[], RecordedTaskInitialization],
        source_ref: EvidenceRef,
        sources: ContextRecords,
        controls: OperationControls,
        *,
        states: StateQualificationChecks,
        initial_checks: Callable[[], InitialObservationChecks],
        comparison: TaskInitialComparison,
        inputs: TaskInitializationInputs | None = None,
    ) -> None:
        if (
            not isinstance(resources, OriginalTaskResourceOwner)
            or not isinstance(preparation, RecordedSiteTaskPreparation)
            or not callable(initialization)
            or not callable(initial_checks)
            or any(v is None for v in (sources, controls, states, comparison))
        ):
            raise TypeError("Original measured source/candidate suppliers required")
        self.resources, self.preparation, self.initialization = (
            resources,
            preparation,
            initialization,
        )
        self.source_ref, self.sources, self.controls = source_ref, sources, controls
        self.states, self.initial_checks, self.comparison = (
            states,
            initial_checks,
            comparison,
        )
        self.inputs = inputs
        if inputs is not None and inputs.plan != resources.plan:
            raise OwnershipConflict("Context body scope changed original task")
        self.reads = resources.owner.reads
        self.baselines = BaselineEvidenceReader(resources.owner.evidence)
        self.resets = ResetEvidenceReader(resources.owner.evidence)
        self.initials = InitialObservationReader(
            resources.owner.evidence, preparation.records
        )

    def read_inputs(
        self,
        receipt: PublicContextReceipt,
        operation: OperationContext,
        control: OperationControl,
    ) -> ContextInputRead | None:
        # Legacy/unaffected consumers retain their original three authority
        # methods. Production owned execution supplies the fixed graph reader.
        if not isinstance(self.sources, ContextFactReads):
            return None
        from .task_context_read import OriginalSourceContextRead

        self.resources.owner.caller(operation, control)
        actual, inputs = self._source_inputs(operation, control)
        if actual != receipt:
            raise OwnershipConflict("Initialization selected another original source")
        self.resources.owner.caller(operation, control)
        control.checkpoint()
        return OriginalSourceContextRead(
            self.resources.owner,
            self.sources,
            self.source_ref,
            actual,
            inputs,
            operation,
            control,
            recheck=self._source_inputs if self.inputs is not None else None,
        )

    def _source_inputs(
        self, op: OperationContext, control: OperationControl
    ) -> tuple[PublicContextReceipt, PublicContextInputs]:
        if not isinstance(self.sources, ContextFactReads):
            raise TypeError("Complete original source reader required")
        self.resources.owner.caller(op, control)
        held = self.inputs
        if held is not None:
            held.check(op, control)
        if held is None or held.source is None:
            actual, inputs = self.sources.load_context_inputs(self.source_ref, op)
            if held is not None:
                held.source = (self.source_ref, actual, inputs)
        else:
            reference, actual, inputs = held.source
            if reference != self.source_ref:
                raise OwnershipConflict("Task input handoff changed original source")
            if assemble_public_context(inputs, actual.operation) != actual:
                raise OwnershipConflict("Task input handoff changed source graph")
        self.sources.check_context_current(op, control)
        self.resources.owner.caller(op, control)
        control.checkpoint()
        return actual, inputs

    def _source(self, op: OperationContext) -> PublicContextReceipt:
        self.resources.owner.caller(op, self.controls.bind(op))
        if self.inputs is not None and isinstance(self.sources, ContextFactReads):
            return self._source_inputs(op, self.controls.bind(op))[0]
        return self.sources.load_context(self.source_ref, op)

    def load_baseline_inputs(
        self,
        request: BaselineReadRequest,
        control: OperationControl,
    ) -> BaselineReadBodies | None:
        if not isinstance(self.sources, BaselineInputReads):
            return None
        request = BaselineReadRequest.model_validate(request)
        self.resources.owner.caller(request.operation, control)
        result = self.sources.load_baseline_inputs(request, control)
        self.resources.owner.caller(request.operation, control)
        control.checkpoint()
        return result

    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        source = self._source(op)
        control = self.controls.bind(op)
        if receipt.scope == source.scope:
            original = self.reads.parse(
                source.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
            )
            if receipt != original or inputs != self.baselines.verify(
                original, control
            ):
                raise OwnershipConflict(
                    "Source baseline differs from original closed source"
                )
            return
        r, p, initial = self.resources, self.preparation, self.initialization()
        s = initial.state
        if (
            initial.plan != r.plan
            or initial.browser is not r.browser()
            or inputs != s.baseline_inputs
            or receipt != s.baseline
            or s.selection is None
            or p.state.environment_selection_ref is None
            or receipt.scope != initial.declaration.scope
        ):
            raise OwnershipConflict(
                "Candidate baseline changed original producer/attempt"
            )
        b = r.browser()
        # The same execute operation's live browser check below includes the
        # complete owner/model/site checks. Distinct initialization/cleanup
        # operations and a non-open browser retain their original general gate.
        # No permit or dynamic check is carried into another semantic boundary.
        if op != r.plan.operation or b is None or b.phase != "open":
            r.require(op, control, live=False)
        if b is None:
            raise OwnershipConflict("Measured candidate browser unavailable")
        if b.phase == "open":
            r.require_browser(r.plan.operation, control)
        else:
            r.original_browser_record(op, control)
        measured = initial.current_initial_observation(op, control)
        if measured is None:
            measured = self.initials.load(
                s.selection, read_operation(inputs.preparation.operation, op), control
            )
        measured = InitialObservationInputs.model_validate(measured)
        held = self.inputs
        if held is not None:
            held.check(op, control)
            if held.candidate_baseline is not None:
                # Exact already-measured immutable inputs, never a live permit.
                # Current owner, model, site and browser were checked above.
                if (
                    held.candidate_baseline_authority is not self
                    or held.candidate_baseline
                    != (inputs, receipt, p.state.environment_selection_ref)
                    or (
                        held.initial != measured
                        or inputs.prepared != measured.prepared
                        or inputs.spec != measured.spec
                        or inputs.observation != measured.observation.record
                    )
                ):
                    raise OwnershipConflict(
                        "Candidate changed original measured baseline inputs"
                    )
                control.checkpoint()
                return
        actual_initial = self.initial_checks().check(measured, control)
        env_ref = p.state.environment_selection_ref
        environment = self.reads.parse(
            env_ref, "environment-selection/1", EnvironmentSelection, control
        )
        actual_environment = self.states.environment(
            environment, env_ref, inputs.environment.operation, control
        )
        if (
            inputs.initial.checks != actual_initial
            or inputs.environment != actual_environment
            or inputs.prepared != measured.prepared
            or inputs.spec != measured.spec
            or inputs.observation != measured.observation.record
            or inputs.observation.sequence != 0
        ):
            raise OwnershipConflict(
                "Candidate baseline differs from complete original measurements"
            )
        if held is not None:
            held.candidate_baseline = (inputs, receipt, env_ref)
            held.candidate_baseline_authority = self

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        source = self._source(op)
        control = self.controls.bind(op)
        original = self.reads.parse(
            source.reset_ref, "reset-receipt/1", ResetReceipt, control
        )
        if (
            receipt.scope != source.scope
            or receipt != original
            or inputs != self.resets.verify(original, control)
        ):
            raise OwnershipConflict(
                "Context authority only reads the original closed source reset"
            )

    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None:
        source = self._source(op)
        if (
            receipt != source
            or inputs.baseline_ref != source.baseline_ref
            or inputs.reset_ref != source.reset_ref
            or inputs.context_ref != source.public_context_ref
        ):
            raise OwnershipConflict(
                "Candidate cannot publish or replace original source context"
            )

    def verify_equivalence(
        self,
        inputs: EquivalenceInputs,
        receipt: EquivalenceReceipt,
        op: OperationContext,
    ) -> None:
        source = self._source(op)
        initial = self.initialization()
        s = initial.state
        control = self.controls.bind(op)
        if (
            inputs.source_ref != self.source_ref
            or inputs.source != source
            or inputs.candidate_inputs != s.baseline_inputs
            or inputs.candidate != s.baseline
            or inputs.candidate_ref != s.baseline_ref
            or receipt != s.equivalence
            or receipt.operation != initial.declaration.equivalence_operation
            or inputs.checks.operation != initial.declaration.comparison_operation
        ):
            raise OwnershipConflict(
                "Equivalence changed original measured source/candidate"
            )
        selected = initial.adoption_checks
        if (None if selected is None else selected.inputs) != inputs.adoption:
            raise OwnershipConflict("Equivalence changed the selected current adoption")
        initial.contexts.facts.verify_adoption(inputs.adoption, op, control)
        # Recompute the declared pure comparison from actual measurements. A
        # recorded `equivalent` string is never sufficient for this authority.
        if inputs.adoption is not None:
            # Ordinary same-owner comparison-body optimization is not applicable
            # to this explicit provenance. Original bytes are read directly;
            # current adoption/resource checks above and below remain mandatory.
            if not isinstance(self.comparison, TaskAdoptedInitialComparison):
                raise TypeError("Current adoption requires its concrete comparison")
            checked = self.comparison.compare_adopted(
                inputs.source_inputs, inputs.candidate_inputs, inputs.adoption, control
            )
        else:
            comparison = self.comparison
            held = self.inputs
            if held is not None and isinstance(comparison, TaskInitialComparisonReads):
                held.check(op, control)
                if held.comparison is None:
                    measured = comparison.read_comparison(
                        inputs.source_inputs, inputs.candidate_inputs, control
                    )
                    held.comparison = (comparison, measured)
                original, measured = held.comparison
                if original is not comparison:
                    raise OwnershipConflict(
                        "Comparison changed original input producer"
                    )
                comparison = measured
            checked = comparison.compare(
                inputs.source_inputs, inputs.candidate_inputs, control
            )
        if inputs.checks.checks != checked:
            raise OwnershipConflict(
                "Equivalence differs from actual original comparison"
            )
        self.resources.require(op, control, live=False)
