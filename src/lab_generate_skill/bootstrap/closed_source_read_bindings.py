"""Explicit source codecs on the same fixed supervised read entry.

Only retained material selects a compiled binding. No executable/permission,
fallback source, runner, session or cached qualification is selected here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from lab_generate_skill.adapters.plans.closed_context import (
    ClosedSourceContextAuthority,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedSourceMaterial,
    ClosedMapReadMaterial,
    ClosedAdminNavigationReadMaterial,
    ClosedGroupReadMaterial,
)
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.lifecycle import OperationControls
from .map_closed_source import (
    ClosedMapSourceDeclarations,
    closed_map_source_context_authority,
    closed_map_source_contexts,
)
from .gitlab_group_closed_source import (
    closed_group_source_authority,
    closed_group_source_contexts,
)
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from .shopping_category_closed_source import (
    closed_category_source_authority,
    closed_category_source_contexts,
)
from .admin_navigation_closed_source import (
    closed_admin_navigation_source_authority,
    closed_admin_navigation_source_contexts,
)


@dataclass(frozen=True)
class ClosedSourceReadBinding:
    authority: Callable[
        [
            PublicContextReceipt,
            BaselineInputs,
            EvidenceStore,
            OperationControls,
            OperationContext,
        ],
        ClosedSourceContextAuthority,
    ]
    contexts: Callable[
        [EvidenceStore, OperationControls, OperationContext], ContextRecords
    ]


def bind_closed_source_read(material: ClosedSourceMaterial) -> ClosedSourceReadBinding:
    if isinstance(material, ClosedMapReadMaterial):
        d = ClosedMapSourceDeclarations(
            material.context_ref,
            material.environment_ref,
            material.reset_ref,
            material.initial,
            material.initial_capture,
            material.site,
            material.browser,
            material.site_record,
            material.browser_record,
        )

        def map_authority(
            source: PublicContextReceipt,
            initial: BaselineInputs,
            evidence: EvidenceStore,
            controls: OperationControls,
            operation: OperationContext,
        ) -> ClosedSourceContextAuthority:
            return closed_map_source_context_authority(
                d, source, initial, evidence, controls, operation
            )

        def map_contexts(
            evidence: EvidenceStore,
            controls: OperationControls,
            operation: OperationContext,
        ) -> ContextRecords:
            return closed_map_source_contexts(d, evidence, controls, operation)

        return ClosedSourceReadBinding(map_authority, map_contexts)
    if isinstance(material, ClosedCategoryNavigationReadMaterial):

        def category_authority(
            source: PublicContextReceipt,
            initial: BaselineInputs,
            evidence: EvidenceStore,
            controls: OperationControls,
            operation: OperationContext,
        ) -> ClosedSourceContextAuthority:
            return closed_category_source_authority(
                material, source, initial, evidence, controls, operation
            )

        def category_contexts(
            evidence: EvidenceStore,
            controls: OperationControls,
            operation: OperationContext,
        ) -> ContextRecords:
            return closed_category_source_contexts(
                material, evidence, controls, operation
            )

        return ClosedSourceReadBinding(category_authority, category_contexts)
    if isinstance(material, ClosedGroupReadMaterial):

        def group_authority(
            source: PublicContextReceipt,
            initial: BaselineInputs,
            evidence: EvidenceStore,
            controls: OperationControls,
            operation: OperationContext,
        ) -> ClosedSourceContextAuthority:
            return closed_group_source_authority(
                material, source, initial, evidence, controls, operation
            )

        def group_contexts(
            evidence: EvidenceStore,
            controls: OperationControls,
            operation: OperationContext,
        ) -> ContextRecords:
            return closed_group_source_contexts(material, evidence, controls, operation)

        return ClosedSourceReadBinding(group_authority, group_contexts)
    d_admin = ClosedAdminNavigationReadMaterial.model_validate(material)

    def admin_authority(
        source: PublicContextReceipt,
        initial: BaselineInputs,
        evidence: EvidenceStore,
        controls: OperationControls,
        operation: OperationContext,
    ) -> ClosedSourceContextAuthority:
        return closed_admin_navigation_source_authority(
            d_admin, source, initial, evidence, controls, operation
        )

    def admin_contexts(
        evidence: EvidenceStore,
        controls: OperationControls,
        operation: OperationContext,
    ) -> ContextRecords:
        return closed_admin_navigation_source_contexts(
            d_admin, evidence, controls, operation
        )

    return ClosedSourceReadBinding(admin_authority, admin_contexts)
