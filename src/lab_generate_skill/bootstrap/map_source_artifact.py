"""Bind an existing Map task artifact without source or recovery actions."""

from dataclasses import fields
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.sites.map.tasks.navigation_spec import (
    NavigationSpec,
    NavigationInputs,
)
from .map_navigation_source import MapNavigationSourceSelection
from .map_closed_source import ClosedMapSourceContexts, ClosedMapSourceDeclarations
from .map_source_publication import PublishedClosedMapQualification
from .source_artifact_inputs import consume_source_inputs


def consume_map_navigation_source(
    owner: OriginalSourceQualificationOwner,
    material: ClosedMapReadMaterial,
    selection: MapNavigationSourceSelection,
    private: NavigationSpec,
    operation: OperationContext,
    controls: OperationControls,
    source_reads: ClosedSourceReadTransport,
) -> PublishedClosedMapQualification:
    material = ClosedMapReadMaterial.model_validate(material)
    private = NavigationSpec.model_validate(private)
    declared = material.site.configuration.map_inputs
    if (
        not isinstance(selection, MapNavigationSourceSelection)
        or not isinstance(declared, MapNavigationWorkerInputs)
        or declared.scope != owner.scope
        or private.task != owner.scope.task
        or declared.native_contract_sha256 != private.native_contract_ref.sha256
        or selection.load(private.native_contract_ref, selection.public_template)
        != private
    ):
        raise OwnershipConflict(
            "Existing Map source changed selected task/version/native contract"
        )
    reader, receipt, inputs = consume_source_inputs(
        owner,
        material,
        private.model_dump_json().encode(),
        private.schema_version,
        operation,
        controls,
        source_reads,
    )
    NavigationInputs(public_task=inputs.context.task, private_spec=private)
    if inputs.context.task.allowed_actions != selection.public_template.allowed_actions:
        raise OwnershipConflict("Existing Map source changed selected public actions")
    declarations = ClosedMapSourceDeclarations(
        **{
            field.name: getattr(material, field.name)
            for field in fields(ClosedMapSourceDeclarations)
        }
    )
    owner.seal(operation, controls.bind(operation))
    return PublishedClosedMapQualification(
        declarations,
        receipt,
        ClosedMapSourceContexts(reader, material.context_ref),
        inputs,
    )
