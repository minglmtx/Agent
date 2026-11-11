"""Original task-bound Shopping recovery facts; not a whole-site ResetReceipt."""

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


def require_new_generation(
    original: NativeServiceQuiescence, current: tuple[NativeNamespaceIdentity, ...]
) -> None:
    known = {x.original.service: x.original for x in original.namespaces}
    if tuple(x.service for x in current) != SERVICE_NAMES:
        raise ValueError(
            "All original Shopping services required in the new generation"
        )
    for pin in current:
        old = known[pin.service]
        if pin == old:
            raise ValueError(
                "New Shopping generation reused a closed namespace identity"
            )
        for before, after in ((old.launcher, pin.launcher), (old.init, pin.init)):
            if (before.node_id, before.boot_id) != (
                after.node_id,
                after.boot_id,
            ) or after.start_ticks < before.start_ticks:
                raise ValueError(
                    "Shopping generation changed original worker host/boot/order"
                )


class OrderEtaRecoverySnapshot(Contract):
    schema_version: Literal["shopping-eta-recovery/1"] = "shopping-eta-recovery/1"
    request: SiteTaskRequest
    state: ShoppingSnapshot
    protected: QueryProtectedState

    @model_validator(mode="after")
    def original_snapshot(self) -> Self:
        if self.request.action != "snapshot":
            raise ValueError("Original pre-task Shopping snapshot required")
        require_stop(self.state.original_stop)
        return self


class OrderEtaRestored(Contract):
    schema_version: Literal["shopping-eta-restored/1"] = "shopping-eta-restored/1"
    request: SiteTaskRequest
    snapshot: OrderEtaRecoverySnapshot
    stopped: NativeServiceQuiescence
    inventory: ShoppingInventory

    @model_validator(mode="after")
    def original_restoration(self) -> Self:
        require_stop(self.stopped)
        require_new_generation(
            self.snapshot.state.original_stop,
            tuple(x.original for x in self.stopped.namespaces),
        )
        if (
            self.request.action != "restore"
            or self.inventory != self.snapshot.state.inventory
            or self.stopped == self.snapshot.state.original_stop
        ):
            raise ValueError(
                "Original snapshot and new stopped generation restoration required"
            )
        return self


class OrderEtaResumed(Contract):
    schema_version: Literal["shopping-eta-resumed/1"] = "shopping-eta-resumed/1"
    request: SiteResumeRequest
    restored: OrderEtaRestored
    protected: QueryProtectedState
    original_pins: tuple[NativeNamespaceIdentity, ...]

    @model_validator(mode="after")
    def recovered_original(self) -> Self:
        if (
            self.request.restore_request != self.restored.request
            or self.protected != self.restored.snapshot.protected
            or tuple(x.service for x in self.original_pins) != SERVICE_NAMES
        ):
            raise ValueError(
                "Original native state and healthy service pins not recovered"
            )
        require_new_generation(self.restored.stopped, self.original_pins)
        return self
