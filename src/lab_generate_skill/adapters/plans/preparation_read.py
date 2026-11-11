"""Original preparation reader in one installed readonly proof."""

from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from .preparation_evidence import PreparationEvidenceReader


def read_preparation_inputs(
    request: PreparationReadRequest,
    material: ClosedSourceMaterial,
    contexts: ContextRecords,
    evidence: EvidenceStore,
    controls: OperationControls,
    control: OperationControl,
    record_operation: OperationContext,
    *,
    current_initial_owner: ResourceOwner | None = None,
) -> PreparationReadBodies:
    request = PreparationReadRequest.model_validate(request)
    op = request.operation
    owner = material.site.token.owner
    task = material.browser.configuration.spec.task.identity
    # Current measurements retain their owner; only qualified source facts use
    # the historical identity. The parent separately checks live stage admission.
    measured_owner = owner if current_initial_owner is None else current_initial_owner
    if (op.run_id, op.owner_id) != (measured_owner.run_id, measured_owner.owner_id):
        raise OwnershipConflict("Preparation read changed original owner")

    # Only immutable qualified-binding facts run in the child. Current caller,
    # claim, producer phase and physical rights remain in the parent authority.
    # Use the original binding algorithm without inventing a live owner object.
    from .qualified_binding_facts import require_qualified_binding_facts
    from lab_generate_skill.domain.task import TaskBinding, PublicTask

    class BindingFacts:
        def verify_binding(
            self,
            binding: TaskBinding,
            public_task: PublicTask,
            private_spec: bytes,
            baseline: bytes,
            operation: OperationContext,
            bounded: OperationControl,
        ) -> None:
            if binding.identity != task:
                raise OwnershipConflict("Preparation changed original source task")
            require_qualified_binding_facts(
                material.context_ref,
                contexts,
                evidence,
                owner,
                binding,
                public_task,
                private_spec,
                baseline,
                operation,
                bounded,
            )

    bindings = EvidenceTaskBindings(evidence, controls, BindingFacts())
    loaded = PreparationEvidenceReader(evidence, bindings).load_with_bodies(
        request.selection, record_operation, control
    )
    if loaded.inputs.environment.scope.owner != measured_owner or (
        loaded.inputs.environment.scope.task != task
        or loaded.inputs.request.operation.attempt_id != op.attempt_id
        or loaded.private_spec is None
        or loaded.snapshot is None
    ):
        raise OwnershipConflict("Preparation proof changed original attempt/inputs")
    return PreparationReadBodies(
        request=request,
        inputs=loaded.inputs,
        verified=tuple(sorted(loaded.verified, key=lambda ref: ref.model_dump_json())),
        private_spec_json=loaded.private_spec.decode(),
        snapshot_json=loaded.snapshot.decode(),
    )
