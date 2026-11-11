"""Bind an existing Admin task artifact without site/browser/native actions."""

from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedAdminNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControls
from .admin_navigation_closed_source import ClosedAdminNavigationSourceContexts
from .admin_navigation_source_publication import PublishedAdminNavigationSource
from .admin_navigation_source_records import AdminNavigationSourceRecordPolicy
from .source_artifact_inputs import consume_source_inputs


def consume_admin_navigation_source(
    owner: OriginalSourceQualificationOwner,
    material: ClosedAdminNavigationReadMaterial,
    raw: bytes,
    native_ref: EvidenceRef,
    public: PublicTask,
    operation: OperationContext,
    controls: OperationControls,
    source_reads: ClosedSourceReadTransport,
) -> PublishedAdminNavigationSource:
    material = ClosedAdminNavigationReadMaterial.model_validate(material)
    policy = AdminNavigationSourceRecordPolicy(raw, native_ref, public)
    declared = material.site.configuration.admin_navigation_inputs
    if (
        material.site.configuration.schema_version != "site-worker-configuration/7"
        or declared is None
        or declared.scope != owner.scope
        or policy.private.task != owner.scope.task
        or declared.native_contract_sha256 != policy.reference.sha256
    ):
        raise OwnershipConflict(
            "Existing Admin source changed selected task/version/native contract"
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
            "Existing Admin source changed public target/start/actions"
        )
    owner.seal(operation, controls.bind(operation))
    return PublishedAdminNavigationSource(
        material,
        receipt,
        ClosedAdminNavigationSourceContexts(reader, material.context_ref),
        inputs,
    )
