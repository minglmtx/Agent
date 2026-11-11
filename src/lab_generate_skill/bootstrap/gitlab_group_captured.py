"""Original Group judgment inputs with a verified closed original browser."""

import hashlib
from lab_generate_skill.adapters.plans.closed_resource import review_resource
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ClosureReceipt,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.sites.gitlab.evidence_schema import GroupEvidence
from lab_generate_skill.sites.gitlab.group_terminal_schema import GroupCapturedSelection
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from .gitlab_group_terminal import read_group_terminal


def read_group_captured(
    store: EvidenceReader,
    preparations: PreparationRecords,
    reference: EvidenceRef,
    contract: EvaluationContract,
    operation: OperationContext,
    control: OperationControl,
) -> GroupEvidence:
    reads = EvaluationEvidence(store, control)
    selected = reads.read(
        reference, "gitlab-group-captured-selection/1", GroupCapturedSelection
    )
    scope = selected.scope
    if (
        operation.run_id,
        operation.owner_id,
        operation.attempt_id,
        contract.identity,
        contract.attempt_id,
    ) != (
        scope.owner.run_id,
        scope.owner.owner_id,
        scope.attempt_id,
        scope.task,
        scope.attempt_id,
    ):
        raise OwnershipConflict(
            "Original Group captured scope required before dependencies"
        )
    terminal = read_group_terminal(
        store, preparations, selected.terminal_ref, contract, operation, control
    )
    if terminal.initial.prepared.scope != scope:
        raise OwnershipConflict("Group capture changed original terminal scope")
    browser = terminal.initial.browser
    record = reads.read(
        selected.browser_record_ref,
        "resource-record/2",
        ResourceRecord,
        limit=64 * 1024**2,
    )
    physical = review_resource(
        record.model_dump(mode="json"), browser.token, store, control
    )
    acquisition = reads.read(
        record.events[1].evidence[0],
        "resource-acquisition-intent/1",
        ResourceAcquisitionIntent,
    )
    closure = reads.read(
        selected.browser_closure_ref, "closure-receipt/1", ClosureReceipt
    )
    if (
        physical["configuration"] != browser.model_dump(mode="json")
        or acquisition.operation != terminal.declaration.browser_acquisition
        or acquisition.configuration_ref.sha256
        != terminal.selection.initial.browser_spec_ref.sha256
        or physical["ending"]["closure"] != closure.model_dump(mode="json")
        or closure.token != browser.token
        or closure.status != "closed"
        or closure.primary_error is not None
    ):
        raise EvidenceIntegrityError(
            "Group captured browser closure changed original physical record"
        )
    intent = reads.read(
        selected.after.intent_ref, "site-capture-intent/2", SiteCaptureIntent
    )
    result = reads.read(selected.after.result_ref, "site-task-result/1", SiteTaskResult)
    prepare, plan = terminal.preparation, terminal.capture_plan
    expected_operation = prepare.operation.model_copy(
        update={
            "operation_id": plan.guard_operation_id,
            "parent_operation_id": closure.operation_id,
            "deadline": terminal.selection.initialized.actor.operation.deadline,
            "cancellation_ref": terminal.selection.initialized.actor.operation.cancellation_ref,
        }
    )
    site = reads.read(
        terminal.environment.site_spec_ref, "site-resource-spec/1", SiteResourceSpec
    )
    if (
        (intent.request.collector_id, intent.request.collector_version)
        != ("gitlab-group-creation", "1")
        or intent.request.inspection
        != prepare.model_copy(
            update={"action": "inspect", "operation": expected_operation}
        )
        or intent.configuration_sha256
        != hashlib.sha256(site.configuration.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != intent.request.digest
    ):
        raise EvidenceIntegrityError(
            "Group final native guard changed original closed-browser lineage"
        )
    evidence = GroupEvidence(
        environment_ref=terminal.selection.environment_selection_ref,
        browser_spec_ref=terminal.selection.initial.browser_spec_ref,
        before=terminal.selection.before,
        after=selected.after,
        page=terminal.selection.page,
        trace_ref=terminal.selection.trace_ref,
    )
    observed = GroupObserved.model_validate_json(result.private_result)
    if (
        observed.model_dump_json() != result.private_result
        or observed.request != intent.request.inspection
        or observed.snapshot != terminal.snapshot
        or observed.native.context != terminal.snapshot.native_before.context
    ):
        raise EvidenceIntegrityError(
            "Group final guard changed original complete snapshot/worker"
        )
    # The original evaluator reads the complete native/project payload once.
    # This wrapper verifies the immutable current capture/closure envelope.
    return evidence
