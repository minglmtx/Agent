"""Category-specific facts over the unchanged complete Shopping restoration."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from ..query_state import QueryProtectedState
from ..snapshot import ShoppingSnapshot, ShoppingInventory, require_stop
from ..services import SERVICE_NAMES
from .order_eta_recovery import require_new_generation
from .navigation_state import CategoryNavigationExecutionInput
from .navigation_contents import NavigationContents


class CategoryNavigationRecoverySnapshot(Contract):
    schema_version: Literal["shopping-category-recovery/1"] = (
        "shopping-category-recovery/1"
    )
    request: SiteTaskRequest
    state: ShoppingSnapshot
    protected: QueryProtectedState
    # Old component-only descriptors remain readable, but cannot establish the
    # new full initial equivalence. The current native producer always fills it.
    contents: NavigationContents | None = None

    @model_validator(mode="after")
    def original_snapshot(self) -> Self:
        data = CategoryNavigationExecutionInput.model_validate_json(
            self.request.private_input
        )
        if (
            self.request.action != "snapshot"
            or self.request.task != data.spec.task
            or data.model_dump_json() != self.request.private_input
        ):
            raise ValueError("Original canonical category snapshot required")
        require_stop(self.state.original_stop)
        if self.contents is not None:
            self.contents.require_snapshot(self.state)
        return self


class CategoryNavigationRestored(Contract):
    schema_version: Literal["shopping-category-restored/1"] = (
        "shopping-category-restored/1"
    )
    request: SiteTaskRequest
    snapshot: CategoryNavigationRecoverySnapshot
    stopped: NativeServiceQuiescence
    inventory: ShoppingInventory

    @model_validator(mode="after")
    def original_restoration(self) -> Self:
        require_stop(self.stopped)
        require_new_generation(
            self.snapshot.state.original_stop,
            tuple(x.original for x in self.stopped.namespaces),
        )
        old, current = self.snapshot.request, self.request
        if (
            current.action != "restore"
            or self.inventory != self.snapshot.state.inventory
            or self.stopped == self.snapshot.state.original_stop
            or any(
                getattr(old, k) != getattr(current, k)
                for k in ("task", "binding_ref", "private_input")
            )
            or any(
                getattr(old.operation, k) != getattr(current.operation, k)
                for k in (
                    "run_id",
                    "owner_id",
                    "attempt_id",
                    "allocation_id",
                    "recovery_ref",
                )
            )
        ):
            raise ValueError(
                "Original category scope and complete restoration required"
            )
        return self


class CategoryNavigationResumed(Contract):
    schema_version: Literal["shopping-category-resumed/1"] = (
        "shopping-category-resumed/1"
    )
    request: SiteResumeRequest
    restored: CategoryNavigationRestored
    protected: QueryProtectedState
    original_pins: tuple[NativeNamespaceIdentity, ...]

    @model_validator(mode="after")
    def recovered_original(self) -> Self:
        if (
            self.request.restore_request != self.restored.request
            or self.protected != self.restored.snapshot.protected
            or tuple(x.service for x in self.original_pins) != SERVICE_NAMES
        ):
            raise ValueError("Original category native state and service pins required")
        require_new_generation(self.restored.stopped, self.original_pins)
        return self
