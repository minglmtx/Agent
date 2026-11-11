"""Independent immutable navigation capture proof, with original four predicates."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    ClosureReceipt,
)
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.sites.shopping_admin.navigation_terminal_schema import (
    AdminNavigationCapturedEvidence,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    AdminNavigationEvidence,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_integrity import (
    NavigationSnapshotIntegrity,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationRecoverySnapshot,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_native_request import (
    NavigationNativeRequestChecks,
)
from .admin_navigation_terminal import read_admin_navigation_terminal


def read_admin_navigation_captured(
    store: EvidenceReader,
    preparations: PreparationRecords,
    reference: EvidenceRef,
    contract: EvaluationContract,
    operation: OperationContext,
    control: OperationControl,
    *,
    initials: InitialObservationReads | None = None,
) -> AdminNavigationEvidence:
    reads = EvaluationEvidence(store, control)
    selected = reads.read(
        reference,
        "admin-navigation-captured-evidence/1",
        AdminNavigationCapturedEvidence,
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
            "Original captured navigation manifest required before dependencies"
        )
    terminal = read_admin_navigation_terminal(
        store,
        preparations,
        selected.terminal_ref,
        contract,
        operation,
        control,
        initials=initials,
    )
    if terminal.initial.prepared.scope != scope:
        raise OwnershipConflict("Captured navigation changed original terminal scope")
    preparation = terminal.preparation
    snapshot_ref = preparation.snapshot_ref
    if snapshot_ref is None or preparation.operation.recovery_ref is None:
        raise EvidenceIntegrityError(
            "Original prepared navigation snapshot/recovery required"
        )
    site = reads.read(
        terminal.environment.site_spec_ref, "site-resource-spec/1", SiteResourceSpec
    )
    declared = site.configuration.admin_navigation_inputs
    initialization = terminal.initial.browser.configuration.initialization
    if (
        declared is None
        or declared.scope != scope
        or site.token.owner != scope.owner
        or not isinstance(initialization, AdminNavigationInitialization)
        or initialization.site_ref != terminal.environment.site_started_ref
        or initialization.endpoint != declared.origin.endpoint
        or initialization.native_contract_sha256 != declared.native_contract_sha256
    ):
        raise EvidenceIntegrityError(
            "Navigation capture changed original native/browser origin and scope"
        )
    original = reads.read(
        snapshot_ref, "admin-navigation-recovery/1", NavigationRecoverySnapshot
    )
    binding = reads.read(preparation.binding_ref, "task-binding/1", TaskBinding)
    recovery = reads.read(
        preparation.operation.recovery_ref, "recovery-plan/1", RecoveryPlan
    )
    environment = reads.read(site.token.recovery_ref, "recovery-plan/1", RecoveryPlan)
    NavigationNativeRequestChecks().verify_inputs(
        site.configuration,
        preparation,
        binding,
        recovery,
        environment,
        original.model_dump_json().encode(),
        original.request,
        control,
    )
    closure = reads.read(
        selected.browser_closure_ref, "closure-receipt/1", ClosureReceipt
    )
    intent = reads.read(
        selected.guard_intent_ref, "site-capture-intent/2", SiteCaptureIntent
    )
    result = reads.read(selected.guard_result_ref, "site-task-result/1", SiteTaskResult)
    request = intent.request
    inspection = request.inspection
    if (
        closure.token != terminal.initial.browser.token
        or closure.status != "closed"
        or (request.collector_id, request.collector_version)
        != ("admin-navigation-snapshot-integrity", "1")
        or intent.configuration_sha256
        != hashlib.sha256(site.configuration.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != request.digest
        or inspection.operation.parent_operation_id != closure.operation_id
        or (
            inspection.task,
            inspection.binding_ref,
            inspection.private_input,
            inspection.snapshot_ref,
        )
        != (
            preparation.task,
            preparation.binding_ref,
            preparation.private_input,
            preparation.snapshot_ref,
        )
    ):
        raise EvidenceIntegrityError(
            "Navigation guard lost original closed browser/configuration/request"
        )
    proof = NavigationSnapshotIntegrity.model_validate_json(result.private_result)
    if (
        proof.model_dump_json() != result.private_result
        or proof.operation != inspection.operation
        or proof.snapshot_ref != snapshot_ref
    ):
        raise EvidenceIntegrityError("Navigation guard changed original verified reply")
    proof.require_original(original)
    control.checkpoint()
    return terminal.selected
