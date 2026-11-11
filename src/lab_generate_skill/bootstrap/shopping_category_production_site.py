"""Actual immutable category site declarations, before the original worker acquires."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from pydantic import TypeAdapter
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.shopping_navigation_origin import ShoppingCategoryOrigin
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec, SiteSlurmBinding
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .shopping_category_navigation import load_category_navigation_inputs
from .shopping_category_site_configuration import shopping_category_site_configuration
from .shopping_category_execution_configuration import category_declaration_reference
from .shopping_category_actor_configuration import category_actor_metadata


@dataclass(frozen=True)
class DeclaredCategoryNavigationSite:
    spec: SiteResourceSpec
    acquisition: OperationContext
    public: PublicTask
    environment: RecoveryPlan
    deferred_acquisition: bool


def declare_category_production_site(
    raw: bytes,
    native_ref: EvidenceRef,
    public: PublicTask,
    scope: StateScope,
    installation: ReleaseInstallation,
    slurm: SiteSlurmBinding,
    origin: ShoppingCategoryOrigin,
    image: ReleaseFile,
    image_source: Path,
    node_root: Path,
    operation: OperationContext,
    *,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    prefix: str,
    site_seconds: int,
    defer_acquisition: bool,
    baseline_ref: EvidenceRef | None = None,
) -> DeclaredCategoryNavigationSite:
    selected = load_category_navigation_inputs(raw, native_ref, public)
    scope = StateScope.model_validate(scope)
    installation = ReleaseInstallation.model_validate(installation)
    slurm = SiteSlurmBinding.model_validate(slurm)
    origin = ShoppingCategoryOrigin.model_validate(origin)
    image = ReleaseFile.model_validate(image)
    operation = OperationContext.model_validate(operation)
    prefix = TypeAdapter(Identifier).validate_python(prefix, strict=True)
    if (
        len(prefix) > 100
        or type(site_seconds) is not int
        or not 1 <= site_seconds <= 7200
        or type(defer_acquisition) is not bool
    ):
        raise ValueError(
            "Explicit bounded original category acquisition declaration required"
        )
    if not isinstance(image_source, Path) or not isinstance(node_root, Path):
        raise TypeError("Original category image/node paths required")
    if (
        scope.task != selected.private_spec.task
        or scope.owner.job_id != slurm.execution.job_id
        or (operation.run_id, operation.owner_id, operation.mode)
        != (scope.owner.run_id, scope.owner.owner_id, "execute")
        or image.sha256 != SHOPPING_IMAGE_SHA
        or public.start_url
        != origin.endpoint.rstrip("/") + selected.private_spec.original.start_path
    ):
        raise OwnershipConflict(
            "Category declaration changed original task/origin/image/owner"
        )
    state = category_navigation_initial_spec(scope.task)
    state_ref = (
        category_declaration_reference(state)
        if baseline_ref is None
        else EvidenceRef.model_validate(baseline_ref)
    )
    if (state_ref.content_schema, state_ref.visibility, state_ref.media_type) != (
        state.schema_version,
        "private",
        "application/json",
    ):
        raise OwnershipConflict(
            "Category site baseline changed original state schema/visibility"
        )
    require_complete_bytes(state_ref, state.model_dump_json().encode())
    environment = RecoveryPlan(
        recovery_id=prefix + ".environment",
        owner=scope.owner,
        baseline_ref=state_ref,
        restore_component_id="shopping-services",
        restore_component_version="1",
        state_coverage=state.environment_reset_checks,
    )
    recovery_ref = category_declaration_reference(environment)
    files = SiteFilesPlan(
        instance_id=prefix + "." + scope.owner.job_id,
        workspace_root=installation.workspace_root,
        source_path=str(image_source),
        node_root=str(node_root),
        image=image,
    )
    token = AllocationToken(
        allocation_id=prefix + ".site",
        owner=scope.owner,
        scope="batch",
        resource_kind="site",
        expected_resource_id=files.instance_id,
        provider_id="fixed-site-worker",
        provider_version="6",
        recovery_ref=recovery_ref,
    )
    configuration = shopping_category_site_configuration(
        selected.private_spec, scope, token, files, installation, origin
    )
    spec = SiteResourceSpec(configuration=configuration, slurm=slurm)
    ceiling = operation.model_copy(
        update={
            "operation_id": token.allocation_id + ".acquire",
            "allocation_id": token.allocation_id,
            "recovery_ref": recovery_ref,
        }
    )
    acquisition = (
        ceiling
        if defer_acquisition
        else ceiling.model_copy(
            update={
                "deadline": min(
                    ceiling.deadline, clock.utcnow() + timedelta(seconds=site_seconds)
                )
            }
        )
    )
    spec.check_operation(acquisition, "execute")
    proposals = (
        (raw, native_ref),
        (state.model_dump_json().encode(), state_ref),
        (environment.model_dump_json().encode(), recovery_ref),
    )
    known = []
    try:
        for body, ref in proposals:
            metadata = EvidenceMetadata.model_validate(
                ref.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            )
            actual = evidence.put(body, metadata, control=controls.bind(operation))
            known.append(actual)
            if actual != ref:
                raise OwnershipConflict(
                    "Category site declaration publication changed exact reference"
                )
    except BaseException as error:
        setattr(error, "category_site_known_references", tuple(known))
        setattr(error, "category_site_candidates", tuple(ref for _, ref in proposals))
        raise
    return DeclaredCategoryNavigationSite(
        spec, acquisition, public, environment, defer_acquisition
    )
