"""Current TaskPreparation port on an explicitly held registered batch site.

Native requests use existing SiteTasks and original source authority. The
TaskExecution RunJournal owns attempt once semantics; this owner-local object
also refuses repeats and keeps every returned reference on partial failure.
It never closes an outer resource or turns preparation into Actor permission.
"""

import json
import os
import threading
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import (
    SiteTaskPreparationPlan,
    SiteTaskPrepared,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.preparation_record import PreparationSelection
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    ResourceJournal,
)
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.state_qualification import EnvironmentQualifications
from lab_generate_skill.ports.task_preparation import TaskPreparationAuthority
from lab_generate_skill.policies.task_preparation import (
    require_original_preparation,
    require_declared_preparation,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from collections.abc import Callable
from lab_generate_skill.ports.site_handle import SiteHandle
from .resource import RegisteredSite
from .retained_resource import RetainedSiteResource
from .task_preparation_state import TaskPreparationState
from .task_preparation_evidence import TaskPreparationEvidence
from lab_generate_skill.ports.task_preparation_inputs import (
    PreparationDeclarationAuthority,
    PreparationDeclarationFacts,
    PreparationDeclarationInputs,
)


class TaskPreparationUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: TaskExecutionPlan,
        phase: str,
        primary: BaseException,
        state: TaskPreparationState,
        on_acquired: Callable[[RegisteredSite], None] | None = None,
    ) -> None:
        self.plan, self.phase, self.primary = plan, phase, primary
        known = list(state.references)
        returned = getattr(primary, "references", ())
        if isinstance(returned, tuple):
            known.extend(ref for ref in returned if isinstance(ref, EvidenceRef))
        qualified = getattr(primary, "qualification_reference", None)
        if isinstance(qualified, EvidenceRef):
            known.append(qualified)
        self.references = tuple(dict.fromkeys(known))
        self.candidates = tuple(
            ref
            for ref in (
                getattr(primary, "preparation_candidate_reference", None),
                getattr(primary, "qualification_candidate_reference", None),
            )
            if isinstance(ref, EvidenceRef)
        )
        self.snapshot_request, self.snapshot_result = (
            state.snapshot_request,
            state.snapshot_result,
        )
        self.snapshot_ref = state.snapshot_ref
        self.prepare_request, self.prepare_result = (
            state.prepare_request,
            state.prepare_result,
        )
        self.environment_ref, self.known_result = state.environment_ref, state.result
        super().__init__(
            "Original task preparation unconfirmed; retain facts, never repeat native requests"
        )


class RecordedSiteTaskPreparation:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        spec: SiteResourceSpec,
        site: SiteHandle,
        resources: ResourceJournal,
        evidence: EvidenceStore,
        controls: OperationControls,
        authority: TaskPreparationAuthority,
        qualifications: EnvironmentQualifications,
        records: PreparationRecords,
        state: TaskPreparationState,
        on_acquired: Callable[[RegisteredSite], None] | None = None,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.declaration = SiteTaskPreparationPlan.model_validate(declaration)
        self.spec = SiteResourceSpec.model_validate(spec)
        if any(
            value is None
            for value in (
                site,
                resources,
                evidence,
                controls,
                authority,
                qualifications,
                records,
                state,
            )
        ):
            raise ValueError(
                "Original held site and every preparation/authority dependency are mandatory"
            )
        self.site, self.resources, self.controls, self.authority = (
            site,
            resources,
            controls,
            authority,
        )
        self.qualifications, self.records, self.state = qualifications, records, state
        if state.phase != "new" or state.references:
            raise ValueError("A fresh owner-local preparation state is required")
        self.on_acquired = on_acquired
        self.io = TaskPreparationEvidence(evidence, state)
        self.reads = StateReads(evidence)
        self.owner = os.getpid(), threading.get_ident()
        self.declared_inputs: PreparationDeclarationInputs | None = None

    def bind_declared_inputs(self, inputs: PreparationDeclarationInputs) -> None:
        if (
            self.state.phase != "new"
            or self.declared_inputs is not None
            or not isinstance(self.authority, PreparationDeclarationAuthority)
        ):
            raise OwnershipConflict(
                "Original unstarted producer and compatible authority required"
            )
        self.authority.use_preparation_inputs(inputs)
        self.declared_inputs = inputs

    def _entry(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
        phase: str,
    ) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Preparation changed original process/thread")
        if self.state.phase != phase:
            raise DispatchAlreadyCommitted(
                "Preparation already attempted or unconfirmed; no new dispatch"
            )
        plan = TaskExecutionPlan.model_validate(plan)
        operation = OperationContext.model_validate(operation)
        scope = self.declaration.scope
        if plan != self.plan or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.mode,
        ) != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id, "execute"):
            raise OwnershipConflict(
                "Preparation changed original frozen task/execute scope"
            )
        control.checkpoint()

    def _declared(
        self, control: OperationControl, operation: OperationContext | None = None
    ) -> tuple[SiteResourceSpec, ResetPlan, TaskBinding]:
        d = self.declaration
        if self.declared_inputs is not None:
            if operation is None:
                raise OwnershipConflict(
                    "Bound declaration bodies require the original operation"
                )
            known = self.declared_inputs.lookup(self.plan, d, operation, control)
            if known is not None:
                if known.site != self.spec:
                    raise OwnershipConflict(
                        "Preparation replaced its original live site"
                    )
                return known.site, known.reset, known.binding
        if (
            self.plan.declaration_ref.content_schema != d.schema_version
            or self.io.read(self.plan.declaration_ref, control)
            != d.model_dump_json().encode()
        ):
            raise OwnershipConflict("Original complete preparation declaration changed")
        spec = self.reads.parse(
            d.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
        )
        reset = self.reads.parse(
            self.plan.reset_plan_ref, "reset-plan/1", ResetPlan, control
        )
        binding = self.reads.parse(
            d.task_binding_ref, "task-binding/1", TaskBinding, control
        )
        if spec != self.spec:
            raise OwnershipConflict("Preparation replaced its original live site")
        if self.declared_inputs is None:
            require_declared_preparation(self.plan, d, reset, spec, binding)
        else:
            assert operation is not None
            self.declared_inputs.record(
                self.plan,
                PreparationDeclarationFacts(d, spec, reset, binding),
                operation,
                control,
            )
        return spec, reset, binding

    def _held(self, operation: OperationContext, control: OperationControl) -> None:
        d, s = self.declaration, self.state
        with self.state.stage("held.declarations"):
            spec, reset, binding = self._declared(control, operation)
        if s.acquired is None or s.acquired_ref is None:
            raise OwnershipConflict("Original acquired binding is not confirmed")
        with self.state.stage("held.acquired-binding"):
            actual = self.reads.parse(
                s.acquired_ref, "site-task-acquired/1", SiteTaskAcquired, control
            )
        if actual != s.acquired:
            raise OwnershipConflict(
                "Acquired binding differs from original saved bytes"
            )
        started = self.reads.parse(
            actual.site_started_ref,
            "site-resource-started/1",
            SiteResourceStarted,
            control,
        )
        if started != self.site.site:
            raise OwnershipConflict("Preparation replaced original acquired startup")
        require_original_preparation(
            self.plan, d, reset, spec, started, binding, actual
        )
        with self.state.stage("held.resource-journal"):
            record = self.resources.read(spec.token, d.resource_read_operation)
        if record.token != spec.token or [e.state for e in record.events] != [
            "registered",
            "acquiring",
            "acquired",
        ]:
            raise OwnershipConflict("Original batch worker is not acquired and open")
        acquired_ref = record.events[2].evidence[0]
        if (
            actual.resource_intent_ref != record.events[1].evidence[0]
            or actual.resource_acquired_ref != acquired_ref
        ):
            raise OwnershipConflict("Acquired binding changed original resource facts")
        intent = self.reads.parse(
            record.events[1].evidence[0],
            "resource-acquisition-intent/1",
            ResourceAcquisitionIntent,
            control,
        )
        private_state_ref(acquired_ref, "site-resource-fact/1")
        with self.state.stage("held.resource-facts"):
            acquired = json.loads(self.io.read(acquired_ref, control))
            startup = json.loads(self.io.read(started.evidence, control))
        if (
            intent.token != spec.token
            or intent.configuration_ref != d.site_spec_ref
            or d.resource_read_operation.parent_operation_id
            != intent.operation.operation_id
        ):
            raise OwnershipConflict("Held site changed original acquisition lineage")
        for fact in (acquired, startup):
            if (
                fact["schema_version"],
                fact["token"],
                fact["spec_sha256"],
                fact["state"],
            ) != (
                "site-resource-fact/1",
                spec.token.model_dump(mode="json"),
                d.site_spec_ref.sha256,
                "acquired",
            ):
                raise OwnershipConflict(
                    "Held startup/worker fact changed original site"
                )
        if acquired["details"]["ready"] != started.ready.model_dump(mode="json") or (
            startup["details"]["ready_ref"] != acquired_ref.model_dump(mode="json")
            or startup["details"]["started"] != started.instance.model_dump(mode="json")
        ):
            raise OwnershipConflict(
                "Site startup is not bound to its original owned worker"
            )
        with self.state.stage("held.source-authority"):
            self.authority.verify(self.plan, d, operation, control)
        control.checkpoint()

    def acquire(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[EvidenceRef, ...]:
        self._entry(plan, operation, control, "new")
        self.state.phase = "binding"
        try:
            with self.state.stage("acquire.declarations"):
                self._declared(control, operation)
            with self.state.stage("acquire.source-authority"):
                self.authority.verify(self.plan, self.declaration, operation, control)
            if isinstance(self.site, RetainedSiteResource):
                with self.state.stage("acquire.site-open"):
                    live = self.site.open(control)
                if self.on_acquired is not None:
                    with self.state.stage("acquire.bind-native"):
                        self.on_acquired(live)
            with self.state.stage("acquire.publish-started"):
                started_ref = self.io.put(self.site.site, control)
            record = self.resources.read(
                self.spec.token, self.declaration.resource_read_operation
            )
            if (
                record.state != "acquired"
                or len(record.events) != 3
                or len(record.events[1].evidence) != 1
                or len(record.events[2].evidence) != 1
            ):
                raise OwnershipConflict("Actual original acquired resource required")
            self.state.acquired = SiteTaskAcquired(
                scope=self.declaration.scope,
                declaration_ref=self.plan.declaration_ref,
                operation=operation,
                site_started_ref=started_ref,
                resource_intent_ref=record.events[1].evidence[0],
                resource_acquired_ref=record.events[2].evidence[0],
            )
            with self.state.stage("acquire.publish-acquired"):
                self.state.acquired_ref = self.io.put(self.state.acquired, control)
            with self.state.stage("acquire.held"):
                self._held(operation, control)
            self.state.phase = "acquired"
            return (
                self.declaration.site_spec_ref,
                self.state.acquired_ref,
                self.declaration.task_binding_ref,
            )
        except BaseException as error:
            self.state.phase = "quarantined"
            raise TaskPreparationUnconfirmed(
                self.plan, "binding", error, self.state
            ) from error

    def _dispatch(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> tuple[EvidenceRef, SiteTaskResult, EvidenceRef]:
        control.checkpoint()
        ref = self.io.put(request, control)
        if request.action == "snapshot":
            self.state.snapshot_request_ref = ref
        else:
            self.state.prepare_request_ref = ref
        self.authority.verify(self.plan, self.declaration, request.operation, control)
        with self.state.stage("native.execute"):
            result = SiteTaskResult.model_validate(
                self.site.tasks.execute_task(request, control=control)
            )
        if request.action == "snapshot":
            self.state.snapshot_result = result
        else:
            self.state.prepare_result = result
        result_ref = self.io.put(result, control)
        if request.action == "snapshot":
            self.state.snapshot_result_ref = result_ref
        else:
            self.state.prepare_result_ref = result_ref
        if result.request_sha256 != request.digest:
            raise OwnershipConflict(
                "Native preparation returned another original request"
            )
        return ref, result, result_ref

    def prepare(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[EvidenceRef, ...]:
        self._entry(plan, operation, control, "acquired")
        self.state.phase = "preparing"
        phase = "admission"
        try:
            self._held(operation, control)
            d, s = self.declaration, self.state
            private = self.io.read(d.private_input_ref, control, 1024**2).decode(
                "utf-8"
            )
            phase = "snapshot"
            snapshot = SiteTaskRequest(
                task=d.scope.task,
                binding_ref=d.task_binding_ref,
                operation=d.snapshot_operation,
                action="snapshot",
                private_input=private,
            )
            s.snapshot_request = snapshot
            ref, result, result_ref = self._dispatch(
                snapshot, self.controls.bind(snapshot.operation)
            )
            s.snapshot_request_ref, s.snapshot_result, s.snapshot_result_ref = (
                ref,
                result,
                result_ref,
            )
            control.checkpoint()
            raw = result.private_result.encode()
            body = json.loads(raw)
            if (
                not isinstance(body, dict)
                or body.get("schema_version") != d.snapshot_schema
                or body.get("request") != snapshot.model_dump(mode="json")
            ):
                raise OwnershipConflict(
                    "Native snapshot changed original schema/request"
                )
            s.snapshot_ref = self.io.put_raw(raw, d.snapshot_schema, control)
            phase = "environment"
            selection = EnvironmentSelection(
                scope=d.scope,
                spec_ref=ResetPlan.model_validate_json(
                    self.io.read(plan.reset_plan_ref, control)
                ).spec_ref,
                site_spec_ref=d.site_spec_ref,
                site_started_ref=self.state.original_acquired().site_started_ref,
                snapshot_ref=s.snapshot_ref,
            )
            s.environment_selection_ref = self.io.put(selection, control)
            s.environment_ref = self.qualifications.publish_environment(
                s.environment_selection_ref, d.environment_operation
            )
            s.references.append(s.environment_ref)
            s.environment = self.qualifications.load_environment(
                s.environment_selection_ref, s.environment_ref, d.environment_operation
            )
            state_spec = self.reads.parse(
                selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
            )
            if (
                s.environment.scope != d.scope
                or s.environment.checks.status != "pass"
                or s.environment.spec_ref != selection.spec_ref
                or s.environment.allocation != self.spec.token
                or s.environment.operation != d.environment_operation
                or s.environment.checks.required != state_spec.environment_checks
            ):
                raise OwnershipConflict(
                    "Original complete environment is not qualified"
                )
            control.checkpoint()
            phase = "prepare"
            request = SiteTaskRequest(
                task=d.scope.task,
                binding_ref=d.task_binding_ref,
                operation=d.prepare_operation,
                action="prepare",
                private_input=private,
                snapshot_ref=s.snapshot_ref,
            )
            s.prepare_request = request
            prep_ref, s.prepare_result, result_ref = self._dispatch(
                request, self.controls.bind(request.operation)
            )
            control.checkpoint()
            phase = "publication"
            selection_prepared = PreparationSelection(
                request_ref=prep_ref,
                result_ref=result_ref,
                environment_ref=s.environment_ref,
            )
            publication = self.records.publish(selection_prepared, request.operation)
            s.references.extend((publication.preparation_ref, publication.prepared_ref))
            prepared = self.records.load(publication, request.operation)
            if (
                prepared.scope != d.scope
                or prepared.task_binding_ref != d.task_binding_ref
            ):
                raise OwnershipConflict(
                    "Prepared result changed original scope/binding"
                )
            if s.acquired_ref is None:
                raise OwnershipConflict("Original acquiring result was not saved")
            s.result = SiteTaskPrepared(
                acquired_ref=s.acquired_ref,
                scope=d.scope,
                declaration_ref=plan.declaration_ref,
                snapshot_request_ref=s.snapshot_request_ref,
                snapshot_result_ref=s.snapshot_result_ref,
                snapshot_ref=s.snapshot_ref,
                environment_selection_ref=s.environment_selection_ref,
                environment_ref=s.environment_ref,
                publication=publication,
            )
            s.result_ref = self.io.put(s.result, control)
            s.phase = "prepared"
            return (s.result_ref, publication.preparation_ref, publication.prepared_ref)
        except BaseException as error:
            self.state.phase = "quarantined"
            raise TaskPreparationUnconfirmed(
                self.plan, phase, error, self.state
            ) from error
