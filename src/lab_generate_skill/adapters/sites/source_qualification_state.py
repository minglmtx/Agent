"""Source-only measured environment/Reset selection permissions, no state algorithm."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
    PendingQualificationNative,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class QualificationStateSelections:
    environment: EnvironmentSelection
    environment_ref: EvidenceRef
    restoration: ResetSelection | None = None
    restoration_ref: EvidenceRef | None = None
    restore: PendingQualificationNative | None = None


class SourceQualificationStateAuthority:
    def __init__(
        self,
        native: SourceQualificationNativeAuthority,
        selections: Callable[[], QualificationStateSelections | None],
    ) -> None:
        if not isinstance(native, SourceQualificationNativeAuthority) or not callable(
            selections
        ):
            raise TypeError(
                "Original source native/resource and measured selection producer required"
            )
        self.native, self.selections = native, selections

    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        acquired = self.native.require_acquired(operation, control)
        known = self.selections()
        if (
            not isinstance(known, QualificationStateSelections)
            or scope != self.native.owner.scope
        ):
            raise OwnershipConflict(
                "Source qualification changed original measured scope"
            )
        read = self.native.reads
        environment = read.parse(
            known.environment_ref,
            "environment-selection/1",
            EnvironmentSelection,
            control,
        )
        if (
            environment != known.environment
            or environment.scope != scope
            or (
                acquired.spec
                if environment.site_spec_ref == acquired.spec_ref
                else read.parse(
                    environment.site_spec_ref,
                    "site-resource-spec/1",
                    SiteResourceSpec,
                    control,
                )
            )
            != self.native.spec
        ):
            raise OwnershipConflict(
                "Source environment changed original acquired site or measured selection"
            )
        if phase == "environment":
            if selection_ref != known.environment_ref:
                raise OwnershipConflict(
                    "Source environment selection differs from original producer"
                )
            return
        if (
            phase != "reset"
            or known.restoration is None
            or known.restoration_ref is None
            or known.restore is None
            or selection_ref != known.restoration_ref
        ):
            raise OwnershipConflict(
                "Source Reset requires original completed restore/resume selection"
            )
        restore = known.restore
        self.native.require_closed_browser(restore, control)
        actual = read.parse(selection_ref, "reset-selection/1", ResetSelection, control)
        if (
            actual != known.restoration
            or actual.environment_selection_ref != known.environment_ref
            or restore.request.action != "restore"
            or read.parse(
                actual.restore_request_ref,
                "site-task-request/2",
                SiteTaskRequest,
                control,
            )
            != restore.request
            or restore.browser_closure_ref is None
            or actual.closure_refs != (restore.browser_closure_ref,)
        ):
            raise OwnershipConflict(
                "Source Reset changed original restore/browser closure lineage"
            )
