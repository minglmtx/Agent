"""Current TaskInitialization: original first return -> qualified Actor request.

No Actor execution or second observation here. Failed initialization retains its
original browser for the separate finalizer; no retry/acquire/capture replay.
"""

from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
import os
import threading
from typing import Any
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.initialization_admission_inputs import (
    InitializationAdmissionInputs,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_preparation import (
    SiteTaskPrepared,
    SiteTaskPreparationPlan,
)
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.preparation import (
    PreparationReceipt,
    EnvironmentBaseline,
    PreparedTask,
)
from lab_generate_skill.domain.initial_observation_publication import (
    PublishedInitialObservation,
)
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    InitialStateChecks,
    assemble_baseline,
)
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceChecks,
    assemble_equivalence,
)
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.ports.task_initialization import (
    TaskInitialMeasurementReads,
    TaskInitialMeasurements,
    TaskInitialComparison,
    TaskAdoptedInitialComparison,
    TaskInitializationAuthority,
    TaskInitializationBodyAuthority,
)
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_adoption import InitialAdoptionAuthority
from lab_generate_skill.ports.contexts import ContextAuthority, ContextInputReads
from lab_generate_skill.ports.state_records import StateAuthority, BaselineInputReads
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.policies.task_initialization import (
    require_original_initialization,
)
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from .task_initialization_state import TaskInitializationState


class TaskInitializationUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: TaskExecutionPlan,
        primary: BaseException,
        state: TaskInitializationState,
        writer: CaptureEvidence,
        failed_phase: str,
    ) -> None:
        self.plan, self.primary, self.state = plan, primary, state
        self.failed_phase = failed_phase
        known = list(state.references)
        for name in (
            "reference",
            "capture_intent_reference",
            "capture_result_reference",
            "initial_checks_reference",
        ):
            ref = getattr(primary, name, None)
            if isinstance(ref, EvidenceRef):
                known.append(ref)
        self.references = tuple(dict.fromkeys(known))
        returned = getattr(primary, "capture_candidate_references", ())
        if not isinstance(returned, tuple):
            returned = ()
        private_candidates = tuple(
            r
            for r in (
                getattr(primary, "initial_checks_candidate_reference", None),
                getattr(primary, "candidate_reference", None),
            )
            if isinstance(r, EvidenceRef)
        )
        self.candidates = tuple(
            dict.fromkeys(
                (
                    *state.candidates,
                    *writer.candidates,
                    *private_candidates,
                    *[r for r in returned if isinstance(r, EvidenceRef)],
                )
            )
        )
        self.known_result = state.result
        super().__init__(
            "Original initialization unconfirmed; retain browser/facts for finalization, never repeat"
        )


class RecordedTaskInitialization:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        declaration_ref: EvidenceRef,
        browser: RetainedBrowserResource,
        preparations: PreparationRecords,
        measurements: TaskInitialMeasurements,
        comparison: TaskInitialComparison,
        authority: TaskInitializationAuthority,
        state_authority: StateAuthority,
        context_authority: ContextAuthority,
        evidence: EvidenceStore,
        controls: OperationControls,
        *,
        inputs: TaskInitializationInputs | None = None,
        adoption_checks: InitialAdoptionAuthority | None = None,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.declaration = TaskInitializationPlan.model_validate(declaration)
        if any(
            x is None
            for x in (
                browser,
                preparations,
                measurements,
                comparison,
                authority,
                state_authority,
                context_authority,
                evidence,
                controls,
            )
        ):
            raise ValueError(
                "Original initialization resources, producers and authorities are mandatory"
            )
        self.declaration_ref, self.browser = declaration_ref, browser
        self.preparations, self.measurements, self.comparison = (
            preparations,
            measurements,
            comparison,
        )
        self.authority, self.evidence, self.controls = authority, evidence, controls
        self.states = EvidenceStateRecords(
            evidence,
            controls,
            state_authority,
            input_reads=(
                state_authority
                if isinstance(state_authority, BaselineInputReads)
                else None
            ),
        )
        if adoption_checks is not None:
            if not isinstance(adoption_checks, InitialAdoptionAuthority):
                raise TypeError("Explicit selected initial-adoption authority required")
            if not isinstance(comparison, TaskAdoptedInitialComparison):
                raise TypeError(
                    "Selected current adoption requires a concrete adopted comparison"
                )
            selected = adoption_checks.inputs
            if (
                selected.binding.scope != self.declaration.scope
                or selected.binding.execution_source_ref != self.plan.source_ref
                or selected.source.intent != self.plan.intent
            ):
                raise OwnershipConflict(
                    "Initializer changed the selected current adoption"
                )
        self.adoption_checks = adoption_checks
        self.contexts = EvidenceContextRecords(
            evidence,
            controls,
            context_authority,
            adoption_checks=adoption_checks,
            input_reads=(
                context_authority
                if isinstance(context_authority, ContextInputReads)
                else None
            ),
            baseline_input_reads=(
                context_authority
                if isinstance(context_authority, BaselineInputReads)
                else None
            ),
        )
        self.reads = StateReads(evidence)
        self.initials = InitialObservationReader(evidence, preparations)
        self.writer = CaptureEvidence(evidence, "task-initialization-v1")
        if inputs is not None and inputs.plan != self.plan:
            raise OwnershipConflict("Initialization body scope changed original plan")
        self.inputs = inputs
        self.state = TaskInitializationState()
        self.owner = os.getpid(), threading.get_ident()
        self._current_initial: InitialObservationInputs | None = None

    def current_initial_observation(
        self, operation: OperationContext, control: OperationControl
    ) -> InitialObservationInputs | None:
        """Only this active start's verified immutable graph; never a live grant."""
        current = self._current_initial
        if current is None and self.inputs is not None:
            self.inputs.check(operation, control)
            current = self.inputs.initial
        if current is None:
            return None
        control.checkpoint()
        late_operations = tuple(
            self.plan.operation.model_copy(
                update={"operation_id": self.plan.operation.operation_id + suffix}
            )
            for suffix in (".capture", ".evaluate")
        )
        if operation in late_operations:
            if self.inputs is None or self.state.phase != "initialized":
                raise OwnershipConflict("Completed owned initial body required")
            self.inputs.check(operation, control)
        if self.owner != (os.getpid(), threading.get_ident()) or operation not in (
            self.declaration.baseline_operation,
            self.declaration.equivalence_operation,
            self.plan.operation,
            self.plan.operation.model_copy(
                update={
                    "operation_id": self.plan.operation.operation_id
                    + ".execution-admission"
                }
            ),
            *late_operations,
        ):
            raise OwnershipConflict("Initial body handoff changed original call/scope")
        if current.selection != self.state.selection:
            raise OwnershipConflict("Initial body handoff changed original selection")
        control.checkpoint()
        return current

    def start(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitializedTask:
        plan = TaskExecutionPlan.model_validate(plan)
        operation = OperationContext.model_validate(operation)
        if self.owner != (os.getpid(), threading.get_ident()) or plan != self.plan:
            raise OwnershipConflict("Initialization changed original controller/plan")
        if self.state.phase != "new":
            raise DispatchAlreadyCommitted(
                "Initialization already attempted; no browser/capture replay"
            )
        d, s = self.declaration, self.state
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.mode,
        ) != (
            d.scope.owner.run_id,
            d.scope.owner.owner_id,
            d.scope.attempt_id,
            "execute",
        ) or (
            operation.deadline > plan.operation.deadline
            or operation.cancellation_ref != plan.operation.cancellation_ref
            or operation.allocation_id is not None
            or operation.recovery_ref is not None
        ):
            raise OwnershipConflict("Initialization changed original execute scope")
        s.phase = "admission"
        try:
            control.checkpoint()
            declared_bytes = self.reads.read(self.declaration_ref, control)
            require_complete_bytes(self.declaration_ref, declared_bytes)
            if (
                self.declaration_ref.content_schema != d.schema_version
                or self.declaration_ref.visibility != "private"
                or declared_bytes != d.model_dump_json().encode()
            ):
                raise OwnershipConflict(
                    "Complete frozen initialization declaration changed"
                )
            original = self.reads.parse(
                d.prepared_result_ref, "site-task-prepared/2", SiteTaskPrepared, control
            )
            declarations = (
                None if self.inputs is None else self.inputs.preparation_declarations
            )
            known = (
                None
                if declarations is None
                else declarations.require(
                    plan, declarations.declaration, operation, control
                )
            )
            if known is not None and original.declaration_ref != plan.declaration_ref:
                raise OwnershipConflict(
                    "Initialization changed the original producer declaration reference"
                )
            prepared_plan = (
                known.declaration
                if known is not None
                else self.reads.parse(
                    original.declaration_ref,
                    "site-task-preparation-plan/2",
                    SiteTaskPreparationPlan,
                    control,
                )
            )
            acquired = self.reads.parse(
                original.acquired_ref, "site-task-acquired/1", SiteTaskAcquired, control
            )
            request = self.reads.parse(
                original.publication.selection.request_ref,
                "site-task-request/2",
                SiteTaskRequest,
                control,
            )
            prepared = PreparedTask.model_validate(
                self.preparations.load(
                    original.publication, read_operation(request.operation, operation)
                )
            )
            environment = self.reads.parse(
                original.environment_ref,
                "environment-baseline/1",
                EnvironmentBaseline,
                control,
            )
            reset = (
                known.reset
                if known is not None
                else self.reads.parse(
                    plan.reset_plan_ref, "reset-plan/1", ResetPlan, control
                )
            )
            if (
                known is not None
                and prepared.task_binding_ref != known.declaration.task_binding_ref
            ):
                raise OwnershipConflict(
                    "Initialization changed the original producer binding reference"
                )
            binding = (
                known.binding
                if known is not None
                else self.reads.parse(
                    prepared.task_binding_ref, "task-binding/1", TaskBinding, control
                )
            )
            admission_inputs = InitializationAdmissionInputs(
                self.declaration_ref,
                d,
                original,
                prepared_plan,
                acquired,
                binding,
                reset,
            )

            def verify(op: OperationContext, gate: OperationControl) -> None:
                if isinstance(self.authority, TaskInitializationBodyAuthority):
                    self.authority.verify_with_inputs(
                        plan, d, admission_inputs, op, gate
                    )
                else:
                    self.authority.verify(plan, d, op, gate)

            source = self.reads.parse(
                d.source_context_receipt_ref,
                "public-context-receipt/1",
                PublicContextReceipt,
                control,
            )
            adoption = (
                None if self.adoption_checks is None else self.adoption_checks.inputs
            )
            source_inputs = self.contexts.facts.context(
                source, operation, control, adoption=adoption
            )
            browser_bytes = self.reads.read(d.browser_spec_ref, control)
            require_complete_bytes(d.browser_spec_ref, browser_bytes)
            if (
                d.browser_spec_ref.content_schema != self.browser.spec.schema_version
                or browser_bytes != self.browser.spec.model_dump_json().encode()
                or self.browser.operation != d.browser_acquisition
            ):
                raise OwnershipConflict(
                    "Initialization changed original browser declaration"
                )
            require_original_initialization(
                plan,
                d,
                original,
                prepared_plan,
                prepared,
                environment,
                source,
                source_inputs,
                reset,
                self.browser.spec,
                acquired,
                request,
                adoption=adoption,
            )
            skill = self.reads.parse(
                plan.skill_ref,
                "compact-skill/1",
                CompactSkill,
                control,
                visibility="public",
            )
            if skill.content_digest != plan.intent.skill_digest:
                raise OwnershipConflict(
                    "Initialization changed original candidate skill"
                )
            self.reads.parse(
                d.actor.context_configuration_ref,
                "actor-context-configuration/1",
                ActorContextConfiguration,
                control,
            )
            self.reads.dependencies((d.actor,), control)
            verify(operation, control)
            control.checkpoint()
            s.phase = "browser"
            session = self.browser.open(control)
            if session.resource_started_ref is None:
                raise OwnershipConflict("Original browser first return is unconfirmed")
            s.references.append(session.resource_started_ref)
            s.selection = InitialObservationSelection(
                preparation=original.publication,
                browser_spec_ref=d.browser_spec_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            s.phase = "initial"
            verify(d.capture_operation, self.controls.bind(d.capture_operation))
            complete = (
                self.measurements.record_complete(s.selection, control)
                if isinstance(self.measurements, TaskInitialMeasurementReads)
                else None
            )
            if (
                isinstance(self.measurements, TaskInitialMeasurementReads)
                and type(complete) is not PublishedInitialObservation
            ):
                raise OwnershipConflict(
                    "Original complete initial publication required"
                )
            initial_ref = EvidenceRef.model_validate(
                complete.reference
                if complete is not None
                else self.measurements.record(s.selection, control)
            )
            s.references.append(initial_ref)
            measured = (
                InitialObservationInputs.model_validate(complete.inputs)
                if complete is not None
                else self.initials.load(s.selection, d.initial_operation, control)
            )
            if complete is not None and (
                measured.selection != s.selection or measured.prepared != prepared
            ):
                raise OwnershipConflict(
                    "Initial input handoff changed original preparation/selection"
                )
            self._current_initial = measured
            if self.inputs is not None:
                self.inputs.check(operation, control)
                self.inputs.initial = measured
            if complete is None:
                initial = self.reads.parse(
                    initial_ref, "initial-state-checks/1", InitialStateChecks, control
                )
            else:
                initial = InitialStateChecks.model_validate(complete.value)
                require_complete_bytes(initial_ref, initial.model_dump_json().encode())
                if (
                    initial_ref.content_schema,
                    initial_ref.visibility,
                    initial_ref.media_type,
                    initial_ref.producer,
                ) != (
                    "initial-state-checks/1",
                    "private",
                    "application/json",
                    "initial-observation-checks-v1",
                ):
                    raise OwnershipConflict(
                        "Initial publication changed schema/visibility"
                    )
            if (
                initial.observation_ref != session.observation_ref
                or initial.scope != d.scope
                or initial.operation != d.initial_operation
            ):
                raise OwnershipConflict(
                    "Initial checks changed original first observation"
                )
            s.phase = "baseline"
            preparation = (
                PreparationReceipt.model_validate(complete.preparation)
                if complete is not None
                else self.reads.parse(
                    original.publication.preparation_ref,
                    "preparation-receipt/1",
                    PreparationReceipt,
                    control,
                )
            )
            if complete is not None:
                require_complete_bytes(
                    original.publication.preparation_ref,
                    preparation.model_dump_json().encode(),
                )
            inputs = BaselineInputs(
                binding=binding,
                public_task=prepared.public_task,
                spec=measured.spec,
                spec_ref=prepared.spec_ref,
                environment=environment,
                environment_ref=original.environment_ref,
                preparation=preparation,
                preparation_ref=original.publication.preparation_ref,
                prepared=prepared,
                prepared_ref=original.publication.prepared_ref,
                observation=measured.observation.record,
                observation_ref=initial.observation_ref,
                initial=initial,
                initial_ref=initial_ref,
            )
            s.baseline_inputs = inputs
            s.baseline = assemble_baseline(inputs, d.baseline_operation)
            s.candidates.append(
                evidence_reference(
                    s.baseline.model_dump_json().encode(),
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="baseline-receipt/1",
                        visibility="private",
                        producer="state-records-v1",
                    ),
                )
            )
            verify(d.baseline_operation, self.controls.bind(d.baseline_operation))
            s.baseline_ref = EvidenceRef.model_validate(
                self.states.publish_baseline_verified(s.baseline, d.baseline_operation)
            )
            s.references.append(s.baseline_ref)
            if s.baseline.status != "ready":
                raise OwnershipConflict("Candidate initial baseline is not ready")
            s.phase = "comparison"
            if adoption is None:
                checks = self.comparison.compare(source_inputs, inputs, control)
            else:
                if not isinstance(self.comparison, TaskAdoptedInitialComparison):
                    raise TypeError("Selected comparison lacks explicit adopted inputs")
                self.contexts.facts.verify_adoption(
                    adoption, d.comparison_operation, control
                )
                checks = self.comparison.compare_adopted(
                    source_inputs, inputs, adoption, control
                )
            fields: dict[str, Any] = (
                {}
                if adoption is None
                else {
                    "schema_version": "equivalence-checks/2",
                    "adoption": adoption.binding,
                }
            )
            facts = EquivalenceChecks(
                **fields,
                scope=d.scope,
                operation=d.comparison_operation,
                source_context_receipt_ref=d.source_context_receipt_ref,
                candidate_baseline_ref=s.baseline_ref,
                checks=checks,
            )
            facts_ref = self.writer.put(
                facts.model_dump_json().encode(), facts.schema_version, control
            )
            s.references.append(facts_ref)
            compared = EquivalenceInputs(
                source_inputs=source_inputs,
                source=source,
                source_ref=d.source_context_receipt_ref,
                candidate_inputs=inputs,
                candidate=s.baseline,
                candidate_ref=s.baseline_ref,
                checks=facts,
                checks_ref=facts_ref,
                adoption=adoption,
            )
            s.equivalence = assemble_equivalence(compared, d.equivalence_operation)
            s.candidates.append(
                evidence_reference(
                    s.equivalence.model_dump_json().encode(),
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema=s.equivalence.schema_version,
                        visibility="private",
                        producer="context-records-v1",
                    ),
                )
            )
            verify(d.equivalence_operation, self.controls.bind(d.equivalence_operation))
            reference, dependencies = self.contexts.publish_equivalence_inputs(
                s.equivalence, compared, d.equivalence_operation
            )
            s.equivalence_ref = EvidenceRef.model_validate(reference)
            if self.inputs is not None:
                self.inputs.check(operation, control)
                self.inputs.equivalence = (reference, compared, dependencies)
            s.references.append(s.equivalence_ref)
            if s.equivalence.status != "equivalent":
                raise OwnershipConflict(
                    "Candidate initial state is not equivalent to original source"
                )
            s.phase = "actor-request"
            actor = ActorRunRequest(
                schema_version="actor-run-request/2",
                scope=d.scope,
                task=prepared.public_task,
                skill=skill,
                initial_observation_ref=initial.observation_ref,
                browser_allocation=self.browser.spec.token,
                operation=plan.operation,
                **d.actor.model_dump(exclude={"schema_version"}),
            )
            s.result = InitializedTask(
                baseline_ref=s.baseline_ref,
                equivalence_ref=s.equivalence_ref,
                actor=actor,
            )
            verify(operation, control)
            control.checkpoint()
            s.phase = "initialized"
            return s.result
        except BaseException as error:
            failed_phase = s.phase
            s.phase = "quarantined"
            failure = TaskInitializationUnconfirmed(
                plan, error, s, self.writer, failed_phase
            )
            raise failure from error
        finally:
            self._current_initial = None
