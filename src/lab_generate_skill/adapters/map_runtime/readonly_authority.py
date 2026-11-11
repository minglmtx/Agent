"""Original closed source ownership for the optional immutable asset projection."""

from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    ClosedSourceContexts,
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.domain.map_readonly_binding import bind_map_readonly_inputs
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.lifecycle import OperationControl


def verify_original_readonly_source(
    owner: ClaimedRunResourceOwner,
    spec: SiteResourceSpec,
    operation: OperationContext,
    control: OperationControl,
) -> None:
    inputs = spec.configuration.map_inputs
    if not isinstance(inputs, MapNavigationWorkerInputs):
        raise OwnershipConflict("Readonly assets require original Map navigation")
    if inputs.runtime.readonly_inputs is None:
        return
    if not isinstance(owner.authority, OriginalExecutionClaimAuthority):
        raise OwnershipConflict("Original claimed source owner required")
    contexts = owner.authority.contexts
    if not isinstance(contexts, ClosedSourceContexts) or not isinstance(
        contexts._records, SupervisedClosedSourceContexts
    ):
        raise OwnershipConflict(
            "Readonly assets require the controlled original source reader"
        )
    records = contexts._records
    material = records.material
    if not isinstance(material, ClosedMapReadMaterial) or (
        material.context_ref != inputs.origin.source_context_receipt_ref
        or material.site.token.owner != spec.token.owner
        or material.site.slurm.execution != spec.slurm.execution
        or material.site.slurm.parent != spec.slurm.parent
        or material.site.configuration.installation != spec.configuration.installation
    ):
        raise OwnershipConflict(
            "Readonly assets changed original closed source/owner/controller/release"
        )
    source = material.site.configuration.map_inputs
    if not isinstance(source, MapNavigationWorkerInputs):
        raise OwnershipConflict("Original navigation source assets required")
    original = MapRuntimeInputs.model_validate(
        inputs.runtime.model_copy(
            update={
                "schema_version": "map-native-runtime-inputs/1",
                "readonly_inputs": None,
            }
        )
    )
    if bind_map_readonly_inputs(original, source.runtime) != inputs.runtime:
        raise OwnershipConflict(
            "Readonly asset projection differs from original source"
        )
    owner.caller(operation, control)
    records.check_context_current(operation, control)
