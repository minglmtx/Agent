"""Consume an existing closed task source on its original controlled ports.

This is a read, never a recovery/replay or source reconstruction fallback. The
installed reader validates the complete historical graph; current owner and
storage permission are independently checked. Site wrappers bind actual task
parameters before returning any published-source object.
"""

from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.policies.publication_inputs import checked_publication_inputs


def consume_source_inputs(
    owner: OriginalSourceQualificationOwner,
    material: ClosedSourceMaterial,
    private_spec: bytes,
    private_schema: str,
    operation: OperationContext,
    controls: OperationControls,
    source_reads: ClosedSourceReadTransport,
) -> tuple[SupervisedClosedSourceContexts, PublicContextReceipt, PublicContextInputs]:
    if not isinstance(owner, OriginalSourceQualificationOwner) or not isinstance(
        source_reads, ClosedSourceReadTransport
    ):
        raise TypeError(
            "Original source owner and controlled installed reader required"
        )
    if type(private_spec) is not bytes or type(private_schema) is not str:
        raise TypeError("Exact original private source bytes and schema required")
    operation = OperationContext.model_validate(operation)
    control = controls.bind(operation)
    owner.require(operation, control, new_work=False)
    if (
        source_reads.store is not owner.evidence
        or material.browser.configuration.spec.scope != owner.scope
        or material.site.token.owner != owner.scope.owner
    ):
        raise OwnershipConflict("Existing source changed current task/scope/store")
    reader = SupervisedClosedSourceContexts(material, source_reads, controls)
    receipt, inputs = reader.load_context_inputs(material.context_ref, operation)
    inputs = checked_publication_inputs(material.context_ref, receipt, inputs)
    private = inputs.baseline_inputs.binding.private_spec_ref
    if (
        receipt.scope != owner.scope
        or private.content_schema != private_schema
        or private.visibility != "private"
        or private.media_type != "application/json"
    ):
        raise OwnershipConflict("Existing source changed exact task/private format")
    require_complete_bytes(private, private_spec)
    owner.require(operation, control, new_work=False)
    control.checkpoint()
    return reader, receipt, inputs
