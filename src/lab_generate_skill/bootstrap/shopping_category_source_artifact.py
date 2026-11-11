"""Read an exact original category source without native/browser effects."""

import hashlib
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from .shopping_category_closed_source import ClosedCategoryNavigationSourceContexts
from .shopping_category_source_publication import PublishedCategoryNavigationSource
from .shopping_category_source_records import CategoryNavigationSourceRecordPolicy
from .source_artifact_inputs import consume_source_inputs


def consume_category_navigation_source(
    owner: OriginalSourceQualificationOwner,
    material: ClosedCategoryNavigationReadMaterial,
    raw: bytes,
    native_ref: EvidenceRef,
    public: PublicTask,
    operation: OperationContext,
    controls: OperationControls,
    source_reads: ClosedSourceReadTransport,
) -> PublishedCategoryNavigationSource:
    material = ClosedCategoryNavigationReadMaterial.model_validate(material)
    policy = CategoryNavigationSourceRecordPolicy(raw, native_ref, public)
    config = material.site.configuration
    declared = config.shopping_category_inputs
    payload = CategoryNavigationExecutionInput(spec=policy.private).model_dump_json()
    if (
        config.schema_version != "site-worker-configuration/9"
        or declared is None
        or declared.scope != owner.scope
        or policy.private.task != owner.scope.task
        or declared.native_contract_sha256 != native_ref.sha256
        or declared.private_input_sha256 != hashlib.sha256(payload.encode()).hexdigest()
        or config.files.image.sha256 != SHOPPING_IMAGE_SHA
    ):
        raise OwnershipConflict(
            "Existing category source changed task/version/native/private/image"
        )
    reader, receipt, inputs = consume_source_inputs(
        owner,
        material,
        policy.private.model_dump_json().encode(),
        policy.private.schema_version,
        operation,
        controls,
        source_reads,
    )
    if inputs.context.task != policy.public:
        raise OwnershipConflict(
            "Existing category source changed public target/start/actions"
        )
    owner.seal(operation, controls.bind(operation))
    return PublishedCategoryNavigationSource(
        material,
        receipt,
        ClosedCategoryNavigationSourceContexts(reader, material.context_ref),
        inputs,
    )
