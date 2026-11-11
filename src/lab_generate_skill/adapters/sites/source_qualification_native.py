"""Original pending source-only native intent, before any execution claim.

Uses the existing source resource journal, task binding reader and site input
rules. This keeps only caller-local once state; it is not another task ledger or
runner. The producer persists an exact intent before the fixed client invokes
this authority. Only snapshot, prepare and closed-browser restore are admitted.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.retained_closure import (
    original_closed_browser,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.task_bindings import TaskBindingEvidenceReader
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    ClosureReceipt,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.ports.site_tasks import SiteTaskInputChecks
from lab_generate_skill.ports.evidence import CurrentEvidenceChecks


@dataclass(frozen=True)
class PendingQualificationNative:
    request: SiteTaskRequest
    request_ref: EvidenceRef
    binding: TaskBinding
    snapshot_request: SiteTaskRequest | None = None
    snapshot_ref: EvidenceRef | None = None
    browser: RetainedBrowserResource | None = None
    browser_closure_ref: EvidenceRef | None = None


@dataclass(frozen=True)
class AcquiredQualificationSite:
    """Exact immutable acquisition facts from this require_acquired call only."""

    intent_ref: EvidenceRef
    intent: ResourceAcquisitionIntent
    spec_ref: EvidenceRef
    spec: SiteResourceSpec


class SourceQualificationNativeAuthority:
    def __init__(
        self,
        owner: OriginalSourceQualificationOwner,
        spec: SiteResourceSpec,
        acquisition: OperationContext,
        journal: ResourceJournal,
        pending: Callable[[], PendingQualificationNative | None],
        inputs: SiteTaskInputChecks,
        *,
        current_evidence: CurrentEvidenceChecks | None = None,
    ) -> None:
        if (
            not isinstance(owner, OriginalSourceQualificationOwner)
            or not callable(pending)
            or inputs is None
        ):
            raise TypeError(
                "Original source owner, pending producer and native input checks required"
            )
        self.owner, self.spec, self.acquisition, self.journal = (
            owner,
            SiteResourceSpec.model_validate(spec),
            OperationContext.model_validate(acquisition),
            journal,
        )
        self.spec.check_operation(self.acquisition, "execute")
        if (spec.token.owner, spec.slurm.execution, spec.slurm.parent) != (
            owner.scope.owner,
            owner.execution,
            owner.controller,
        ):
            raise OwnershipConflict(
                "Source native caller changed original site/controller"
            )
        self.pending, self.inputs = pending, inputs
        self.reads = StateReads(owner.evidence)
        self.bindings = TaskBindingEvidenceReader(owner.evidence)
        self._dispatched: list[str] = []
        # This authority is constructed for one source qualification invocation.
        # Only exact immutable bodies survive between its consumers, never a
        # caller/ledger/storage decision. Legacy callers still read each time.
        self.current_evidence = current_evidence
        self._acquired_inputs: AcquiredQualificationSite | None = None

    def close_input_read(self) -> None:
        self._acquired_inputs = None

    def require_acquired(
        self, operation: OperationContext, control: OperationControl
    ) -> AcquiredQualificationSite:
        """Original acquired facts for source record readers; no dispatch grant."""
        self.owner.require_caller(operation, control)
        op = self.acquisition.model_copy(
            update={
                "operation_id": operation.operation_id + ".source-resource-read",
                "mode": "cleanup",
                "parent_operation_id": self.acquisition.operation_id,
                "cancellation_ref": None,
                "deadline": operation.deadline,
            }
        )
        record = self.journal.read(self.spec.token, op)
        if (
            record.token != self.spec.token
            or record.state != "acquired"
            or len(record.events) != 3
            or len(record.events[1].evidence) != 1
        ):
            raise OwnershipConflict(
                "Source native request requires its original acquired site"
            )
        if self.current_evidence is not None:
            self.current_evidence.check_current(control)
            known = self._acquired_inputs
            if known is not None:
                if record.events[1].evidence[0] != known.intent_ref:
                    raise OwnershipConflict(
                        "Source acquisition changed complete intent reference"
                    )
                control.checkpoint()
                return known
        intent = self.reads.parse(
            record.events[1].evidence[0],
            "resource-acquisition-intent/1",
            ResourceAcquisitionIntent,
            control,
        )
        if intent.token != self.spec.token or intent.operation != self.acquisition:
            raise OwnershipConflict(
                "Source native request changed original site acquisition"
            )
        spec = self.reads.parse(
            intent.configuration_ref, "site-resource-spec/1", SiteResourceSpec, control
        )
        if spec != self.spec:
            raise OwnershipConflict(
                "Source native request changed original site acquisition"
            )
        control.checkpoint()
        result = AcquiredQualificationSite(
            record.events[1].evidence[0], intent, intent.configuration_ref, spec
        )
        if self.current_evidence is not None:
            self.current_evidence.check_current(control)
            self._acquired_inputs = result
        return result

    def require_closed_browser(
        self, selected: PendingQualificationNative, control: OperationControl
    ) -> None:
        b, ref = selected.browser, selected.browser_closure_ref
        if (
            b is None
            or ref is None
            or b.phase != "closed"
            or b.spec.configuration.spec.scope != self.owner.scope
        ):
            raise OwnershipConflict(
                "Source restore requires original closed observation browser"
            )
        op = b.operation.model_copy(
            update={
                "operation_id": selected.request.operation.operation_id
                + ".source-browser-read",
                "mode": "cleanup",
                "parent_operation_id": b.operation.operation_id,
                "cancellation_ref": None,
                "deadline": selected.request.operation.deadline,
            }
        )
        record = original_closed_browser(
            b.spec, b.operation, op, b.journal, self.owner.evidence, control
        )
        ending = json.loads(self.reads.read(record.events[-1].evidence[0], control))
        closure = self.reads.parse(ref, "closure-receipt/1", ClosureReceipt, control)
        if (
            closure.model_dump(mode="json") != ending["details"]["closure"]
            or closure.token != b.spec.token
            or closure.status != "closed"
        ):
            raise OwnershipConflict(
                "Source restore changed original browser closure bytes"
            )

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        request = SiteTaskRequest.model_validate(request)
        self.owner.require(
            request.operation, control, new_work=request.action != "restore"
        )
        if (
            configuration != self.spec.configuration
            or request.task != self.owner.scope.task
        ):
            raise OwnershipConflict(
                "Source native request changed original configuration/task"
            )
        request.check_site(configuration)
        expected_order = ("snapshot", "prepare", "restore")
        if (
            len(self._dispatched) >= 3
            or request.action != expected_order[len(self._dispatched)]
        ):
            raise DispatchAlreadyCommitted(
                "Source native requests must be once-only snapshot, prepare, restore"
            )
        selected = self.pending()
        if (
            not isinstance(selected, PendingQualificationNative)
            or selected.request != request
        ):
            raise OwnershipConflict(
                "Source native request is not awaiting its original dispatch"
            )
        if (
            selected.request_ref.producer != "source-qualification-native-v1"
            or self.reads.parse(
                selected.request_ref, "site-task-request/2", SiteTaskRequest, control
            )
            != request
        ):
            raise OwnershipConflict(
                "Source native intent changed original producer or bytes"
            )
        self.require_acquired(request.operation, control)
        binding = self.bindings.load(request.binding_ref, control)
        # Resolve every original dependency. The mandatory site input codec
        # below proves canonical execution bytes against the private spec pin;
        # an execution envelope need not equal the private spec serialization.
        self.bindings.dependencies(binding, control)
        if binding != selected.binding:
            raise OwnershipConflict("Source native task binding/private input changed")
        assert request.operation.recovery_ref is not None
        recovery = self.reads.parse(
            request.operation.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        environment = self.reads.parse(
            configuration.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        snapshot: bytes | None = None
        if request.action != "snapshot":
            if (
                request.snapshot_ref is None
                or request.snapshot_ref != selected.snapshot_ref
                or selected.snapshot_request is None
            ):
                raise OwnershipConflict(
                    "Source native effect requires its exact original snapshot"
                )
            snapshot = self.reads.read(request.snapshot_ref, control)
        self.inputs.verify_inputs(
            configuration,
            request,
            binding,
            recovery,
            environment,
            snapshot,
            selected.snapshot_request,
            control,
        )
        if request.action == "restore":
            self.require_closed_browser(selected, control)
        self.owner.require(
            request.operation, control, new_work=request.action != "restore"
        )
        # Any failure after this acknowledgement remains the same unknown call.
        # Neither this supplier nor a new Python object authorizes an RPC replay.
        self._dispatched.append(request.action)
