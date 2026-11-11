"""Two explicit Shopping contracts over the same full-instance state proofs."""

from typing import Literal
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_checks import InitialStateSpec
from .order_eta_spec import OrderEtaSpec
from .order_eta_admission import task_input as eta_input, same_snapshot as eta_snapshot
from .order_eta_recovery import (
    OrderEtaRecoverySnapshot,
    OrderEtaRestored,
    OrderEtaResumed,
)
from .order_eta_policy import order_eta_initial_spec
from .navigation_spec import CategoryNavigationSpec
from .navigation_admission import (
    task_input as category_input,
    same_snapshot as category_snapshot,
)
from .navigation_recovery import (
    CategoryNavigationRecoverySnapshot,
    CategoryNavigationRestored,
    CategoryNavigationResumed,
)
from .navigation_policy import category_navigation_initial_spec

Private = OrderEtaSpec | CategoryNavigationSpec
Snapshot = OrderEtaRecoverySnapshot | CategoryNavigationRecoverySnapshot
Restored = OrderEtaRestored | CategoryNavigationRestored
Resumed = OrderEtaResumed | CategoryNavigationResumed


class ShoppingTaskStateCodec:
    def __init__(
        self,
        task: TaskIdentity,
        family: Literal["recorded_order_eta", "page_navigation"],
    ) -> None:
        task = TaskIdentity.model_validate(task)
        if task.family != family:
            raise ValueError("Shopping state consumer changed its explicit family")
        self.category = family == "page_navigation"
        self.policy: InitialStateSpec = (
            category_navigation_initial_spec(task)
            if self.category
            else order_eta_initial_spec(task)
        )

    @property
    def private_type(self) -> type[Private]:
        return CategoryNavigationSpec if self.category else OrderEtaSpec

    @property
    def private_schema(self) -> str:
        return (
            "shopping-category-navigation/1"
            if self.category
            else "shopping-recorded-order-eta/1"
        )

    @property
    def snapshot_type(self) -> type[Snapshot]:
        return (
            CategoryNavigationRecoverySnapshot
            if self.category
            else OrderEtaRecoverySnapshot
        )

    @property
    def snapshot_schema(self) -> str:
        return (
            "shopping-category-recovery/1"
            if self.category
            else "shopping-eta-recovery/1"
        )

    @property
    def restored_type(self) -> type[Restored]:
        return CategoryNavigationRestored if self.category else OrderEtaRestored

    @property
    def resumed_type(self) -> type[Resumed]:
        return CategoryNavigationResumed if self.category else OrderEtaResumed

    @property
    def recovery_component(self) -> str:
        return "shopping-category-navigation" if self.category else "shopping-order-eta"

    def private(self, request: SiteTaskRequest) -> Private:
        return (
            category_input(request).spec if self.category else eta_input(request).spec
        )

    def same_snapshot(
        self,
        request: SiteTaskRequest,
        snapshot: Snapshot,
        reference: EvidenceRef | None,
    ) -> None:
        if self.category and isinstance(snapshot, CategoryNavigationRecoverySnapshot):
            category_snapshot(request, snapshot, reference)
        elif not self.category and isinstance(snapshot, OrderEtaRecoverySnapshot):
            eta_snapshot(request, snapshot, reference)
        else:
            raise ValueError("Shopping state changed selected snapshot contract")
