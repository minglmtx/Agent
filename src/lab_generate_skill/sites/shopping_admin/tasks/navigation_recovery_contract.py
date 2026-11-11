"""Native navigation snapshot/restore facts, without product creation.

These descriptors are neither source qualification nor a safe ResetReceipt.
The parent must retain their exact bytes and verify original writer closure.
"""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from ..state_contract import AdminStateSnapshot, AdminStateRestored
from ..frontend_contract import AdminFrontendStopped
from .navigation_spec import AdminNavigationSpec
from .navigation_contents_schema import NavigationContents
from .navigation_equivalence_contents import NavigationEquivalenceContents


class NavigationExecutionInput(Contract):
    schema_version: Literal["admin-navigation-execution-input/1"] = (
        "admin-navigation-execution-input/1"
    )
    spec: AdminNavigationSpec


class NavigationRecoverySnapshot(Contract):
    schema_version: Literal["admin-navigation-recovery/1"] = (
        "admin-navigation-recovery/1"
    )
    request: SiteTaskRequest
    state: AdminStateSnapshot
    # Legacy software descriptors cannot establish cross-instance equivalence.
    # The current native producer always measures this before returning.
    contents: NavigationContents | NavigationEquivalenceContents | None = None

    @model_validator(mode="after")
    def original(self) -> Self:
        if self.request.action != "snapshot":
            raise ValueError("Navigation recovery requires original snapshot command")
        data = NavigationExecutionInput.model_validate_json(self.request.private_input)
        if (
            data.spec.task != self.request.task
            or data.model_dump_json() != self.request.private_input
        ):
            raise ValueError("Navigation snapshot changed canonical task specification")
        if self.contents is not None:
            self.contents.require_snapshot(self.state)
        return self


class NavigationPrepared(Contract):
    schema_version: Literal["admin-navigation-prepared/1"] = (
        "admin-navigation-prepared/1"
    )
    task: TaskIdentity
    snapshot_ref: EvidenceRef
    private_spec_sha256: Sha256
    state_snapshot_sha256: Sha256
    initialization: Literal[
        "fixed_local_start_not_original_trajectory_start",
        "declared_local_start; original goal unchanged",
    ]
    start_path: str
    preparation: Literal["no_task_mutation_before_browser_navigation"] = (
        "no_task_mutation_before_browser_navigation"
    )

    @model_validator(mode="after")
    def snapshot(self) -> Self:
        private_state_ref(self.snapshot_ref, "admin-navigation-recovery/1")
        return self


class NavigationRestored(Contract):
    schema_version: Literal["admin-navigation-restored/1"] = (
        "admin-navigation-restored/1"
    )
    task: TaskIdentity
    operation: OperationContext
    snapshot_ref: EvidenceRef
    state: AdminStateRestored
    frontend: AdminFrontendStopped

    @model_validator(mode="after")
    def restored(self) -> Self:
        private_state_ref(self.snapshot_ref, "admin-navigation-recovery/1")
        if (
            self.operation.mode != "cleanup"
            or self.frontend.service != self.state.search.original.service
        ):
            raise ValueError("Navigation restore changed cleanup or original frontend")
        return self
