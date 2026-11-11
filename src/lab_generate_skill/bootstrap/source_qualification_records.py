"""Original source immutable definition/preparation helpers, no task execution."""

from dataclasses import dataclass
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    recovery_seconds,
)
from typing import Protocol
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
    PendingQualificationNative,
)
from lab_generate_skill.adapters.sites.source_qualification_records import (
    SourceQualificationRecordAuthority,
    QualificationTaskDefinition,
    QualificationPreparationFacts,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata, Visibility
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    AllocationToken,
)
from lab_generate_skill.domain.preparation_record import PreparationSelection
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.lifecycle import (
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.site_handle import SiteHandle
from .source_qualification_progress import SourceQualificationProgress
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.adapters.sites.source_preparation_inputs import (
    SourcePreparationInputs,
)


@dataclass(frozen=True)
class SourceRecordDefinition:
    public: PublicTask
    private: Contract
    private_input: str
    spec: InitialStateSpec
    registration_id: str
    restore_component_id: str


class SourceRecordPolicy(Protocol):
    def definition(
        self,
        owner: OriginalSourceQualificationOwner,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
        control: OperationControl,
    ) -> SourceRecordDefinition: ...
    def preparations(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        bindings: EvidenceTaskBindings,
        authority: SourceQualificationRecordAuthority,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
    ) -> EvidencePreparationRecords: ...
    def snapshot_bytes(
        self, request: SiteTaskRequest, result: SiteTaskResult
    ) -> tuple[str, bytes]: ...


class SourceQualificationRecords:
    def __init__(
        self,
        owner: OriginalSourceQualificationOwner,
        native: SourceQualificationNativeAuthority,
        site: SiteHandle,
        policy: SourceRecordPolicy,
        progress: SourceQualificationProgress,
        controls: OperationControls,
        clock: Clock,
        prefix: str,
        *,
        recovery_budgets: SourceRecoveryBudgets | None = None,
        reuse_inputs: bool = False,
    ) -> None:
        self.owner, self.native, self.site, self.policy = owner, native, site, policy
        self.recovery_budgets = (
            None
            if recovery_budgets is None
            else SourceRecoveryBudgets.model_validate(recovery_budgets)
        )
        self.definition: SourceRecordDefinition | None = None
        self.progress, self.controls, self.clock, self.prefix = (
            progress,
            controls,
            clock,
            prefix,
        )
        self.reads = StateReads(owner.evidence)
        self.input_bodies = SourcePreparationInputs(native) if reuse_inputs else None
        self.binding: TaskBinding | None = None
        self.binding_ref: EvidenceRef | None = None
        self.bindings: EvidenceTaskBindings | None = None
        self.records: EvidencePreparationRecords | None = None
        self.spec: InitialStateSpec | None = None
        self.spec_ref: EvidenceRef | None = None
        self.recovery_ref: EvidenceRef | None = None

    def put(
        self, value: Contract, op: OperationContext, visibility: Visibility = "private"
    ) -> EvidenceRef:
        schema = value.model_dump().get("schema_version")
        if type(schema) is not str:
            raise TypeError("Versioned original source contract required")
        return self.raw(value.model_dump_json().encode(), schema, op, visibility)

    def raw(
        self,
        raw: bytes,
        schema: str,
        op: OperationContext,
        visibility: Visibility = "private",
    ) -> EvidenceRef:
        control = self.controls.bind(op)
        self.owner.require_caller(op, control)
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility=visibility,
            producer="source-qualification-native-v1",
        )
        candidate = evidence_reference(raw, metadata)
        try:
            ref = self.owner.evidence.put(raw, metadata, control=control)
        except BaseException as error:
            setattr(error, "source_qualification_candidate_reference", candidate)
            raise
        self.progress.references.append(ref)
        if ref != candidate:
            raise OwnershipConflict("Source record publication changed original bytes")
        return ref

    def task_operation(self, name: str) -> OperationContext:
        if self.recovery_ref is None:
            raise OwnershipConflict("Original source task recovery is not declared")
        return self.native.acquisition.model_copy(
            update={
                "operation_id": self.prefix + "." + name,
                "attempt_id": self.owner.scope.attempt_id,
                "recovery_ref": self.recovery_ref,
            }
        )

    def define(self, operation: OperationContext) -> AllocationToken:
        self.native.require_acquired(operation, self.controls.bind(operation))
        cfg = self.native.spec.configuration
        definition = self.policy.definition(
            self.owner, cfg, self.site.site.instance, self.controls.bind(operation)
        )
        self.definition = definition
        public, private, spec = definition.public, definition.private, definition.spec
        environment = self.reads.parse(
            cfg.token.recovery_ref,
            "recovery-plan/1",
            RecoveryPlan,
            self.controls.bind(operation),
        )
        if (
            self.reads.parse(
                environment.baseline_ref,
                "initial-state-spec/1",
                InitialStateSpec,
                self.controls.bind(operation),
            )
            != spec
        ):
            raise OwnershipConflict(
                "Source definition changed full original baseline declaration"
            )
        self.spec, self.spec_ref = spec, environment.baseline_ref
        binding = TaskBinding(
            identity=public.identity,
            registration_id=definition.registration_id,
            public_task_ref=self.put(public, operation, "public"),
            private_spec_ref=self.put(private, operation),
            baseline_ref=self.spec_ref,
        )
        authority = SourceQualificationRecordAuthority(
            self.native,
            QualificationTaskDefinition(
                binding, public, private.model_dump_json().encode(), spec
            ),
            self.site,
            lambda: self.progress.preparation,
        )
        self.binding = binding
        self.bindings = EvidenceTaskBindings(
            self.owner.evidence, self.controls, authority
        )
        self.binding_ref = self.bindings.publish(binding, operation)
        self.progress.references.append(self.binding_ref)
        original_records = self.policy.preparations(
            self.owner.evidence,
            self.controls,
            self.bindings,
            authority,
            cfg,
            self.site.site.instance,
        )
        self.records = EvidencePreparationRecords(
            original_records.store,
            original_records.controls,
            original_records.reader.bindings,
            original_records.checks,
            original_records.authority,
            input_reads=original_records.input_reads,
            record_inputs=(
                original_records.record_inputs
                if self.input_bodies is None
                else self.input_bodies.records
            ),
        )
        recovery = RecoveryPlan(
            recovery_id=self.prefix + ".task-recovery",
            owner=self.owner.scope.owner,
            attempt_id=self.owner.scope.attempt_id,
            baseline_ref=self.spec_ref,
            restore_component_id=definition.restore_component_id,
            restore_component_version="1",
            state_coverage=spec.task_reset_checks,
        )
        self.recovery_ref = self.put(recovery, operation)
        browser_recovery = RecoveryPlan(
            recovery_id=self.prefix + ".browser-close",
            owner=self.owner.scope.owner,
            attempt_id=self.owner.scope.attempt_id,
            baseline_ref=self.spec_ref,
            restore_component_id="browser-close",
            restore_component_version="1",
            state_coverage=("browser-processes",),
        )
        browser = AllocationToken(
            allocation_id=self.prefix + ".browser-allocation",
            owner=self.owner.scope.owner,
            scope="attempt",
            attempt_id=self.owner.scope.attempt_id,
            resource_kind="browser",
            expected_resource_id=self.prefix + ".browser-instance",
            provider_id="fixed-browser-worker",
            provider_version="3",
            recovery_ref=self.put(browser_recovery, operation),
        )
        self.progress.reset_plan = ResetPlan(
            scope=self.owner.scope,
            parent_operation_id=self.prefix + ".prepare",
            spec_ref=self.spec_ref,
            task_recovery_ref=self.recovery_ref,
            environment_recovery_ref=cfg.token.recovery_ref,
            attempt_allocations=(browser,),
        )
        self.progress.reset_plan_ref = self.put(self.progress.reset_plan, operation)
        return browser

    def request(
        self, action: str, operation: OperationContext
    ) -> tuple[SiteTaskRequest, SiteTaskResult, EvidenceRef, EvidenceRef]:
        if self.binding is None or self.binding_ref is None or self.definition is None:
            raise OwnershipConflict("Original source task definition required")
        request = SiteTaskRequest.model_validate(
            {
                "task": self.owner.scope.task,
                "binding_ref": self.binding_ref,
                "operation": operation,
                "action": action,
                "snapshot_ref": (
                    None if action == "snapshot" else self.progress.snapshot_ref
                ),
                "private_input": self.definition.private_input,
            }
        )
        ref = self.put(request, operation)
        self.progress.pending_native = PendingQualificationNative(
            request,
            ref,
            self.binding,
            snapshot_request=self.progress.snapshot_request,
            snapshot_ref=self.progress.snapshot_ref,
            browser=self.progress.browser,
            browser_closure_ref=self.progress.browser_closure_ref,
        )
        result = self.site.tasks.execute_task(
            request, control=self.controls.bind(operation)
        )
        if result.request_sha256 != request.digest:
            raise OwnershipConflict(
                "Source native result belongs to another original request"
            )
        result_ref = self.put(result, operation)
        if action == "snapshot":
            schema, raw = self.policy.snapshot_bytes(request, result)
            self.progress.snapshot_request = request
            self.progress.snapshot_ref = self.raw(raw, schema, operation)
        elif action == "prepare":
            self.progress.prepare_request, self.progress.prepare_result = (
                request,
                result,
            )
        return request, result, ref, result_ref

    def publish_preparation(self) -> None:
        p = self.progress
        if (
            self.records is None
            or p.prepare_request is None
            or p.prepare_result is None
            or p.environment is None
            or p.environment_ref is None
        ):
            raise OwnershipConflict(
                "Actual source preparation/environment required before publication"
            )
        p.preparation = QualificationPreparationFacts(
            p.prepare_request, p.prepare_result, p.environment
        )
        op = p.prepare_request.operation.cleanup(
            self.prefix + ".prepare-record",
            now=self.clock.utcnow(),
            seconds=recovery_seconds(
                self.recovery_budgets, "preparation_metadata_seconds", 1800
            ),
        )
        selected = PreparationSelection(
            request_ref=self.put(p.prepare_request, op),
            result_ref=self.put(p.prepare_result, op),
            environment_ref=p.environment_ref,
        )
        p.publication = self.records.publish(selected, op)
        if self.input_bodies is not None:
            self.input_bodies.records.expect_publication(p.publication)
