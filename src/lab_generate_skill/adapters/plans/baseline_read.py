"""Use the original complete baseline algorithm inside the fixed readonly proof."""

from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
    BaselineReadBody,
    baseline_documents,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.lifecycle import OperationControl
from .baseline_evidence import BaselineEvidenceReader
from .qualified_binding_facts import require_qualified_binding_facts


def read_baseline_inputs(
    request: BaselineReadRequest,
    material: ClosedSourceMaterial,
    contexts: ContextRecords,
    evidence: EvidenceStore,
    control: OperationControl,
    record_operation: OperationContext,
    *,
    current_initial_owner: ResourceOwner | None = None,
) -> BaselineReadBodies:
    request = BaselineReadRequest.model_validate(request)
    owner = material.site.token.owner
    measured_owner = owner if current_initial_owner is None else current_initial_owner
    if (
        request.receipt.scope.owner != measured_owner
        or (request.operation.run_id, request.operation.owner_id)
        != (measured_owner.run_id, measured_owner.owner_id)
        or request.receipt.scope.task
        != material.browser.configuration.spec.task.identity
    ):
        raise OwnershipConflict("Baseline read changed original source owner/task")
    result = baseline_input_bodies(request, evidence, control)
    inputs = result.inputs
    require_qualified_binding_facts(
        material.context_ref,
        contexts,
        evidence,
        owner,
        inputs.binding,
        inputs.public_task,
        evidence.read(inputs.binding.private_spec_ref, control=control),
        evidence.read(inputs.binding.baseline_ref, control=control),
        record_operation,
        control,
    )
    return result


def baseline_input_bodies(
    request: BaselineReadRequest,
    evidence: EvidenceStore,
    control: OperationControl,
) -> BaselineReadBodies:
    request = BaselineReadRequest.model_validate(request)
    inputs = BaselineEvidenceReader(evidence).verify(request.receipt, control)
    refs = tuple(
        dict.fromkeys(
            (
                *(ref for ref, _ in baseline_documents(inputs)),
                inputs.prepared.recovery_ref,
                inputs.environment.allocation.recovery_ref,
            )
        )
    )
    bodies = tuple(
        BaselineReadBody(
            reference=ref, json_text=evidence.read(ref, control=control).decode()
        )
        for ref in refs
    )
    by_ref = {body.reference: body.json_text for body in bodies}
    task = RecoveryPlan.model_validate_json(by_ref[inputs.prepared.recovery_ref])
    environment = RecoveryPlan.model_validate_json(
        by_ref[inputs.environment.allocation.recovery_ref]
    )
    return BaselineReadBodies(
        request=request,
        inputs=inputs,
        bodies=bodies,
        verified=tuple(dict.fromkeys(evidence_references((inputs, task, environment)))),
    )
