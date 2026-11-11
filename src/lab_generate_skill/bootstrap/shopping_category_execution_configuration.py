"""Freeze category phase declarations for the existing original owned task.

Validate complete data joins before publication. A fresh original source/claim
proof precedes CAS writes; no site, browser, model or recovery action runs here.
"""

import hashlib
from pydantic import TypeAdapter
from lab_generate_skill.adapters.sites.resource_records import (
    reference as site_resource_reference,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.validation import Contract, Identifier
from lab_generate_skill.evaluators.shopping.navigation import REQUIREMENTS
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.policies.publication_inputs import checked_publication_inputs
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from .execution_source_admission import AdmittedExecutionSource
from .shopping_category_source_publication import PublishedCategoryNavigationSource
from .task_execution_bindings import TaskExecutionDeclarations


def category_declaration_reference(value: Contract) -> EvidenceRef:
    schema = value.model_dump().get("schema_version")
    if type(schema) is not str:
        raise TypeError("Versioned category declaration required")
    return evidence_reference(
        value.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="shopping-category-production-inputs-v1",
        ),
    )


def prepare_category_execution_configuration(
    source: PublishedCategoryNavigationSource,
    admission: AdmittedExecutionSource,
    inputs: ExecutionTaskInputs,
    private: CategoryNavigationSpec,
    scope: StateScope,
    site: SiteResourceSpec,
    acquisition: OperationContext,
    environment: RecoveryPlan,
    operation: OperationContext,
    read_operation: OperationContext,
    *,
    evidence: EvidenceStore,
    controls: OperationControls,
    prefix: str,
    metadata_cleanup_seconds: int,
    physical_close_seconds: int,
) -> TaskExecutionDeclarations:
    if not isinstance(source, PublishedCategoryNavigationSource) or not isinstance(
        admission, AdmittedExecutionSource
    ):
        raise TypeError("Original category publication and claimed source required")
    inputs = ExecutionTaskInputs.model_validate(inputs)
    private = CategoryNavigationSpec.model_validate(private)
    scope = StateScope.model_validate(scope)
    site = SiteResourceSpec.model_validate(site)
    acquisition = OperationContext.model_validate(acquisition)
    environment = RecoveryPlan.model_validate(environment)
    operation = OperationContext.model_validate(operation)
    read_operation = OperationContext.model_validate(read_operation)
    prefix = TypeAdapter(Identifier).validate_python(prefix, strict=True)
    if (
        len(prefix) > 100
        or type(metadata_cleanup_seconds) is not int
        or type(physical_close_seconds) is not int
        or not 1 <= physical_close_seconds <= 60
        or not physical_close_seconds <= metadata_cleanup_seconds <= 3600
    ):
        raise ValueError(
            "Explicit bounded category phase/metadata/physical limits required"
        )
    site.check_operation(acquisition, "execute")
    checked = checked_publication_inputs(
        source.material.context_ref, source.receipt, source.inputs
    )
    baseline = checked.baseline_inputs
    task = baseline.binding
    selected = site.configuration.shopping_category_inputs
    original = admission.published.source
    owner = scope.owner
    native = CategoryNavigationExecutionInput(spec=private)
    if (
        selected is None
        or evidence is not admission.reader.reads.store
        or evidence is not admission.authority.reads.store
        or controls is not admission.authority.controls
        or site.configuration.schema_version != "site-worker-configuration/9"
        or selected.scope != scope
        or site.configuration.installation
        != source.material.site.configuration.installation
        or selected.native_contract_sha256 != private.native_contract_ref.sha256
        or selected.private_input_sha256
        != hashlib.sha256(native.model_dump_json().encode()).hexdigest()
        or private.task != scope.task
        or task.identity != scope.task
        or original.task != task
        or original.run.owner != owner
        or original.intent.binding.attempt_id != scope.attempt_id
        or original.source_context_receipt_ref != source.material.context_ref
        or inputs.task_binding_ref != baseline.prepared.task_binding_ref
        or inputs.source_context_receipt_ref != source.material.context_ref
        or inputs.attempt_id != scope.attempt_id
        or source.receipt.scope.owner != owner
        or source.receipt.scope.task != scope.task
        or source.receipt.scope.attempt_id == scope.attempt_id
        or source.receipt.scope.context_id == scope.context_id
        or environment.owner != owner
        or environment.attempt_id is not None
        or environment.baseline_ref != task.baseline_ref
        or environment.state_coverage != baseline.spec.environment_reset_checks
        or (environment.restore_component_id, environment.restore_component_version)
        != ("shopping-services", "1")
    ):
        raise OwnershipConflict(
            "Category task declaration changed source/private/candidate/recovery joins"
        )
    require_complete_bytes(task.private_spec_ref, private.model_dump_json().encode())
    require_complete_bytes(
        site.token.recovery_ref, environment.model_dump_json().encode()
    )
    records: list[tuple[Contract, EvidenceRef]] = []

    def planned(value: Contract) -> EvidenceRef:
        reference = category_declaration_reference(value)
        records.append((value, reference))
        return reference

    records.append((environment, site.token.recovery_ref))
    native_ref = planned(native)
    task_recovery = RecoveryPlan(
        recovery_id=prefix + ".task-recovery",
        owner=owner,
        attempt_id=scope.attempt_id,
        baseline_ref=task.baseline_ref,
        restore_component_id="shopping-category-navigation",
        restore_component_version="1",
        state_coverage=baseline.spec.task_reset_checks,
    )
    task_recovery_ref = planned(task_recovery)
    browser_recovery = RecoveryPlan(
        recovery_id=prefix + ".browser-close",
        owner=owner,
        attempt_id=scope.attempt_id,
        baseline_ref=task.baseline_ref,
        restore_component_id="browser-close",
        restore_component_version="1",
        state_coverage=("browser-processes",),
    )
    browser = AllocationToken(
        allocation_id=prefix + ".browser",
        owner=owner,
        scope="attempt",
        attempt_id=scope.attempt_id,
        resource_kind="browser",
        expected_resource_id=prefix + ".browser-instance",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=planned(browser_recovery),
    )
    execute = operation.model_copy(
        update={"operation_id": prefix + ".task", "attempt_id": scope.attempt_id}
    )

    def phase(name: str, recovery: EvidenceRef) -> OperationContext:
        return execute.model_copy(
            update={
                "operation_id": prefix + "." + name,
                "allocation_id": site.token.allocation_id,
                "recovery_ref": recovery,
            }
        )

    prepare = phase("prepare", task_recovery_ref)
    reset = ResetPlan(
        scope=scope,
        parent_operation_id=prepare.operation_id,
        spec_ref=task.baseline_ref,
        task_recovery_ref=task_recovery_ref,
        environment_recovery_ref=site.token.recovery_ref,
        attempt_allocations=(browser,),
    )
    site_ref = site_resource_reference(
        site.model_dump_json().encode(), site.schema_version
    )
    records.append((site, site_ref))
    declaration = SiteTaskPreparationPlan(
        scope=scope,
        site_spec_ref=site_ref,
        task_binding_ref=inputs.task_binding_ref,
        private_input_ref=native_ref,
        snapshot_schema="shopping-category-recovery/1",
        snapshot_operation=phase("snapshot", task_recovery_ref),
        prepare_operation=prepare,
        environment_operation=phase("environment", site.token.recovery_ref),
        resource_read_operation=acquisition.model_copy(
            update={
                "operation_id": prefix + ".resource-read",
                "mode": "cleanup",
                "parent_operation_id": acquisition.operation_id,
                "cancellation_ref": None,
                "deadline": operation.deadline,
            }
        ),
    )
    capture = TaskCapturePlan(
        schema_version="task-capture-plan/2",
        scope=scope,
        requirements=REQUIREMENTS,
        page_operation_id=prefix + ".page",
        close_operation_id=prefix + ".capture-close",
        guard_operation_id=prefix + ".guard",
        page_collector_id="shopping-category-navigation-page",
        page_collector_version="1",
        guard_collector_id="shopping-category-navigation",
        guard_collector_version="1",
        close_seconds=physical_close_seconds,
        metadata_close_seconds=metadata_cleanup_seconds,
    )
    final = TaskFinalizationPlan(
        scope=scope,
        browser_close_operation_id=prefix + ".final-close",
        restore_operation_id=prefix + ".restore",
        resume_operation_id=prefix + ".resume",
        qualification_operation_id=prefix + ".reset-facts",
        reset_operation_id=prefix + ".safe-reset",
    )
    reset_ref, declaration_ref = planned(reset), planned(declaration)
    capture_ref, final_ref = planned(capture), planned(final)
    plan = TaskExecutionPlan(
        schema_version="task-execution-plan/2",
        intent=original.intent,
        source_ref=admission.published.source_ref,
        reset_plan_ref=reset_ref,
        declaration_ref=declaration_ref,
        skill_ref=inputs.skill_ref,
        evaluation=EvaluationContract(
            identity=scope.task,
            attempt_id=scope.attempt_id,
            task_contract_ref=inputs.task_binding_ref,
            public_task_ref=task.public_task_ref,
            completion_spec_ref=task.private_spec_ref,
            scope="engineering",
            requirements=REQUIREMENTS,
        ),
        operation=execute,
        read_operation=read_operation,
        cleanup_seconds=metadata_cleanup_seconds,
    )
    ids = {
        execute.operation_id,
        prepare.operation_id,
        declaration.snapshot_operation.operation_id,
        declaration.environment_operation.operation_id,
        capture.page_operation_id,
        capture.close_operation_id,
        capture.guard_operation_id,
        final.browser_close_operation_id,
        final.restore_operation_id,
        final.resume_operation_id,
        final.qualification_operation_id,
        final.reset_operation_id,
    }
    if ids & checked.operation_ids:
        raise OwnershipConflict(
            "Candidate declarations reused completed source operations"
        )
    control = controls.bind(operation)
    facts = admission.reader.load(plan, operation, control)
    if (
        facts.inputs != inputs
        or facts.run.resources.cleanup_timeout_seconds != metadata_cleanup_seconds
    ):
        raise OwnershipConflict(
            "Category declaration changed current claimed inputs/budget"
        )
    known: list[EvidenceRef] = []
    try:
        for value, reference in records:
            metadata = EvidenceMetadata.model_validate(
                reference.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            )
            actual = evidence.put(
                value.model_dump_json().encode(), metadata, control=control
            )
            known.append(actual)
            if actual != reference:
                raise OwnershipConflict(
                    "Category declaration publication changed original reference"
                )
        current = admission.claims.require_source(
            original.intent.binding.claim_ref, original.run, original.task, operation
        )
        check_source_claim(
            current, original.intent.binding.claim_ref, original.run, original.task
        )
        control.checkpoint()
    except BaseException as error:
        setattr(error, "category_declaration_known_references", tuple(known))
        setattr(
            error,
            "category_declaration_candidates",
            tuple(reference for _, reference in records),
        )
        raise
    return TaskExecutionDeclarations(
        plan, declaration, reset, capture, capture_ref, final, final_ref
    )
