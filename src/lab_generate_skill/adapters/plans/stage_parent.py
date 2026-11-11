"""Verify retained parent bodies; current permission is always checked separately.

Immutable data may be retained with explicit live storage checks. Legacy readers
without those checks reread authorization; no allow decision is cached.
"""

import hashlib
import json
from dataclasses import dataclass
from lab_generate_skill.domain.actor_step import ActorStepClosed
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    ClosureReceipt,
    OperationContext,
    ResourceRecord,
)
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.reset import ResetReceipt
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.site_resource import SiteStepClosed
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.stage_validation_admission import (
    StageValidationAuthorization,
)
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.evidence import EvidenceReader, CurrentEvidenceChecks
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from .baseline_evidence import BaselineEvidenceReader
from .reset_evidence import ResetEvidenceReader
from .state_reads import StateReads


@dataclass(frozen=True)
class VerifiedStageParent:
    authorization: StageValidationAuthorization
    source: ExecutionTaskSource
    context: PublicContextReceipt


class RetainedStageParentChecks:
    def __init__(
        self,
        origin: FrozenExecutionOrigin,
        binding: SourceClaimBinding,
        authorization_id: str,
        evidence: EvidenceReader,
        controls: OperationControls,
        *,
        current_checks: CurrentEvidenceChecks | None = None,
    ) -> None:
        self.origin = FrozenExecutionOrigin.model_validate(origin)
        self.binding = SourceClaimBinding.model_validate(binding)
        self.origin.validation.require_current_binding(self.binding)
        self.authorization_id, self.reads, self.controls = (
            authorization_id,
            StateReads(evidence),
            controls,
        )
        self.current_checks = current_checks
        self._verified_origin: FrozenExecutionOrigin | None = None
        self._data: VerifiedStageParent | None = None

    def verify_parent(
        self, validation: SourceStageValidation, operation: OperationContext
    ) -> None:
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        control.checkpoint()
        if validation != self.origin.validation or (
            operation.run_id,
            operation.owner_id,
        ) != (self.binding.run.owner.run_id, self.binding.run.owner.owner_id):
            raise OwnershipConflict(
                "Parent proof changed configured validation/current caller scope"
            )
        if self.current_checks is not None:
            self.current_checks.check_current(control)
        if self._data is not None and self._verified_origin != self.origin:
            raise OwnershipConflict("Retained parent changed its verified origin")
        authorization = (
            self._data.authorization
            if self.current_checks is not None and self._data is not None
            else self.reads.parse(
                validation.authorization_ref,
                validation.authorization_ref.content_schema,
                StageValidationAuthorization,
                control,
            )
        )
        if (
            authorization.authorization_id != self.authorization_id
            or authorization.binding != self.binding
            or authorization.parent_claim_ref != validation.parent.reference
            or authorization.parent_source_ref != self.origin.parent_source_ref
            or authorization.stage_scope != validation.stage_scope
        ):
            raise OwnershipConflict(
                "Stage authorization differs from trusted selected inputs"
            )
        if self._data is None:
            self._data = self._verify(authorization, control)
            self._verified_origin = self.origin
        elif self._data.authorization != authorization:
            raise OwnershipConflict("Immutable parent authorization changed")
        if self.current_checks is not None:
            self.current_checks.check_current(control)
        control.checkpoint()

    def data(self, operation: OperationContext) -> VerifiedStageParent:
        self.verify_parent(self.origin.validation, operation)
        assert self._data is not None
        return self._data

    def _verify(
        self, authorization: StageValidationAuthorization, control: OperationControl
    ) -> VerifiedStageParent:
        read = self.reads.parse
        evidence = self.reads.store
        parent = self.origin.validation.parent
        source = read(
            self.origin.parent_source_ref,
            "execution-task-source/1",
            ExecutionTaskSource,
            control,
        )
        if (
            source.schema_version != "execution-task-source/1"
            or source.run != parent.record.binding.run
            or source.task != parent.record.binding.task
            or source.intent.binding.claim_ref != parent.reference
        ):
            raise OwnershipConflict(
                "Parent source differs from its original complete claim"
            )
        context = read(
            source.source_context_receipt_ref,
            "public-context-receipt/1",
            PublicContextReceipt,
            control,
        )
        inputs = authorization.parent_evidence
        snapshot = read(inputs.run_ref, "run-journal-snapshot/2", RunSnapshot, control)
        trace = read(
            inputs.trace_ref, "trace-journal-snapshot/1", TraceSnapshot, control
        )
        initialized = read(
            inputs.initialized_ref, "initialized-task/1", InitializedTask, control
        )
        run, attempts = snapshot.project()
        view = trace.project()
        if (
            snapshot.binding != source.run
            or run.stage != "sealed"
            or run.stop_reason != "error"
            or len(attempts) != 1
            or attempts[0].stage != "sealed"
            or any(
                event.stage in ("captured", "evaluated") for event in attempts[0].events
            )
            or attempts[0].binding != trace.plan.binding
            or trace.plan.binding.run != source.run
            or trace.plan.binding.claim_ref != parent.reference
            or trace.plan.scope != initialized.actor.scope
            or view.sealed is None
            or view.sealed.stop_reason != "error"
            or any(
                getattr(view, name) is not None
                for name in ("intent", "generation", "action", "reading")
            )
            or not view.turns
            or any(
                turn.generation.status != "completed"
                or (turn.decision is not None and turn.decision.outcome != "invalid")
                or turn.interaction is not None
                or turn.reading is not None
                for turn in view.turns
            )
            or context.scope.owner != source.run.owner
            or context.scope.task != source.task.identity
        ):
            raise OwnershipConflict(
                "Parent is not a closed, known, pre-business invalid-proposal attempt"
            )
        source_baseline = read(
            context.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
        )
        executed_baseline = read(
            initialized.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
        )
        source_inputs = BaselineEvidenceReader(evidence).verify(
            source_baseline, control
        )
        executed_inputs = BaselineEvidenceReader(evidence).verify(
            executed_baseline, control
        )
        if (
            source_baseline.status != "ready"
            or executed_baseline.status != "ready"
            or source_baseline.scope != context.scope
            or executed_baseline.scope != trace.plan.scope
            or initialized.actor.initial_observation_ref
            != executed_inputs.observation_ref
        ):
            raise OwnershipConflict(
                "Parent initialization/baselines lost original ready scope"
            )
        resets = tuple(
            read(ref, "reset-receipt/1", ResetReceipt, control)
            for ref in inputs.reset_refs
        )
        if (
            context.reset_ref not in inputs.reset_refs
            or any(reset.status != "safe" for reset in resets)
            or sum(reset.scope == context.scope for reset in resets) != 1
            or sum(reset.scope == trace.plan.scope for reset in resets) != 1
        ):
            raise OwnershipConflict(
                "Both original source and execution safe resets required"
            )
        reset_inputs = [
            ResetEvidenceReader(evidence).verify(reset, control) for reset in resets
        ]
        wanted: dict[str, AllocationToken] = {}
        for token in (
            source_inputs.environment.allocation,
            executed_inputs.environment.allocation,
            initialized.actor.model_allocation,
            initialized.actor.browser_allocation,
            *(closure.token for reset in reset_inputs for closure in reset.closures),
        ):
            if token.allocation_id in wanted and wanted[token.allocation_id] != token:
                raise OwnershipConflict(
                    "Parent allocation identity changed across evidence"
                )
            wanted[token.allocation_id] = token
        resources = tuple(
            read(ref, "resource-record/2", ResourceRecord, control)
            for ref in inputs.resource_refs
        )
        if len(resources) != len(wanted) or {
            record.token.allocation_id for record in resources
        } != set(wanted):
            raise OwnershipConflict(
                "Parent resource inventory is incomplete or duplicated"
            )
        for record in resources:
            if (
                record.token != wanted[record.token.allocation_id]
                or record.token.owner != source.run.owner
                or record.state != "closed"
            ):
                raise OwnershipConflict(
                    "Original parent resource is not closed under its owner"
                )
            self._closed_resource(record, control)
        return VerifiedStageParent(authorization, source, context)

    def verify_closed_resource(
        self, record: ResourceRecord, control: OperationControl
    ) -> None:
        """Verify original physical closure facts; this grants no current work."""
        self._closed_resource(record, control)

    def _closed_resource(
        self, record: ResourceRecord, control: OperationControl
    ) -> None:
        if (
            len(record.events) < 4
            or record.events[1].state != "acquiring"
            or len(record.events[-1].evidence) != 1
        ):
            raise OwnershipConflict("Incomplete original resource history")
        intent = self.reads.parse(
            record.events[1].evidence[0],
            "resource-acquisition-intent/1",
            ResourceAcquisitionIntent,
            control,
        )
        if (
            intent.token != record.token
            or intent.operation != record.events[1].operation
        ):
            raise OwnershipConflict("Parent resource acquisition changed")
        reference = record.events[-1].evidence[0]
        fact = json.loads(self.reads.read(reference, control))
        if (
            fact["token"] != record.token.model_dump(mode="json")
            or fact["operation"] != record.events[-1].operation.model_dump(mode="json")
            or fact["spec_sha256"] != intent.configuration_ref.sha256
            or hashlib.sha256(
                self.reads.read(intent.configuration_ref, control)
            ).hexdigest()
            != intent.configuration_ref.sha256
        ):
            raise OwnershipConflict(
                "Parent resource fact differs from original binding"
            )
        closed: ActorStepClosed | SiteStepClosed | BrowserStepClosed
        if reference.content_schema == "actor-resource-fact/1":
            details = fact
            if fact["kind"] != "closed":
                raise OwnershipConflict("Actor closure is unconfirmed")
            closed = ActorStepClosed.model_validate_json(
                json.dumps(details["step_closed"])
            )
        else:
            details = fact["details"]
            if fact["state"] != "closed":
                raise OwnershipConflict("Resource closure is unconfirmed")
            closure = ClosureReceipt.model_validate_json(json.dumps(details["closure"]))
            if (
                closure.token != record.token
                or closure.status != "closed"
                or closure.primary_error is not None
            ):
                raise OwnershipConflict("Original complete resource closure required")
            if reference.content_schema == "site-resource-fact/1":
                closed = SiteStepClosed.model_validate_json(
                    json.dumps(details["step_closed"])
                )
            elif reference.content_schema == "browser-resource-fact/1":
                closed = BrowserStepClosed.model_validate_json(
                    json.dumps(details["step_closed"])
                )
            else:
                raise OwnershipConflict("Unsupported parent resource closure schema")
        termination = details["termination"]
        if (
            details["cleanup_errors"]
            or termination["state"] != "reaped"
            or termination["cleanup_errors"]
        ):
            raise OwnershipConflict("Parent resource process closure is unconfirmed")
        if closed.target.execution.job_id != record.token.owner.job_id:
            raise OwnershipConflict(
                "Parent closed step belongs to a different original job"
            )
        self.reads.read(closed.evidence, control)
