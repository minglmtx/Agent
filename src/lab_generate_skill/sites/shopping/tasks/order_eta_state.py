"""Private native order/history facts, preserving the old complete reference."""

from typing import Literal, Self
import math
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.identity import TaskIdentity
from ..query_state import QueryProtectedState
from .order_eta_spec import OrderEtaSpec, OrderNumber, RecordedDate

SOURCE_HASHES = {
    "vendor/magento/module-sales/Model/Order/Status/History.php": "80e88fffd5d1729c0758e4130d0c4e8a3e99f2e63053466b987c0fcb0329dce9",
    "vendor/magento/module-sales/Model/ResourceModel/Order/Status/History.php": "bf4a0586eac6cf38cda5bcf9288117c6c5623201379997b1f12d9f6d6a8249a5",
    "vendor/magento/module-sales/view/frontend/templates/order/order_comments.phtml": "c57457ed1367582f34b5b223b53c3e999b537ba42f6f8c1d501a478efd5cb53e",
}
NativeRow = dict[str, str | int | float | None]


class OrderEtaExecutionInput(Contract):
    schema_version: Literal["shopping-eta-execution/1"] = "shopping-eta-execution/1"
    spec: OrderEtaSpec


class NativeEtaFixture(Contract):
    order_id: int = Field(ge=1)
    order_number: OrderNumber
    customer_id: int = Field(ge=1)
    date: RecordedDate
    order: NativeRow
    history_note: NativeRow
    native_history_rows: tuple[NativeRow, ...] = Field(min_length=1)
    initialized_native_visible_note: Literal[True]
    fixture_version: Literal["native-local-recorded-order-date-v1"]
    source_hashes: dict[str, Sha256]
    external_delivery: Literal[False]

    @model_validator(mode="after")
    def owned_visible_record(self) -> Self:
        # Validate the calendar too; model facts are not exempt from private
        # contract validation merely because a fixed native program emitted them.
        OrderEtaSpec.calendar_date(self.date)
        o, h = self.order, self.history_note
        if not {
            "entity_id",
            "customer_id",
            "increment_id",
            "created_at",
            "status",
        } <= set(o) or not {
            "entity_id",
            "parent_id",
            "comment",
            "status",
            "created_at",
            "is_visible_on_front",
            "is_customer_notified",
            "entity_name",
        } <= set(
            h
        ):
            raise ValueError("Original native order/history fields missing")
        if any(
            isinstance(v, float) and not math.isfinite(v)
            for row in (o, h, *self.native_history_rows)
            for v in row.values()
        ):
            raise ValueError("Native SQL rows cannot contain nonfinite values")
        if (
            str(o.get("entity_id")),
            str(o.get("customer_id")),
            o.get("increment_id"),
        ) != (str(self.order_id), str(self.customer_id), self.order_number):
            raise ValueError("Native original order ownership changed")
        if (
            str(h.get("parent_id")),
            h.get("comment"),
            str(h.get("is_visible_on_front")),
            str(h.get("is_customer_notified")),
            h.get("entity_name"),
        ) != (
            str(self.order_id),
            "Recorded estimated delivery date: " + self.date,
            "1",
            "0",
            "order",
        ):
            raise ValueError(
                "Native visible history record differs from declared fixture"
            )
        if (
            sum(x == h for x in self.native_history_rows) != 1
            or self.source_hashes != SOURCE_HASHES
        ):
            raise ValueError("Missing exact native history/source implementation")
        return self


class OrderEtaState(Contract):
    schema_version: Literal["shopping-eta-state/1"] = "shopping-eta-state/1"
    task: TaskIdentity
    fixture: NativeEtaFixture
    protected: QueryProtectedState

    def check(self, spec: OrderEtaSpec) -> None:
        if (self.task, self.fixture.order_number, self.fixture.date) != (
            spec.task,
            spec.order_number,
            spec.recorded_date,
        ):
            raise ValueError(
                "Observed native ETA state changed the selected private task"
            )

    def legacy_reference(self) -> dict[str, object]:
        source = self.fixture.model_dump(mode="json")
        source.update(
            complete_native_protection=self.protected.protection.model_dump(
                mode="json"
            ),
            native_static_assets=self.protected.native_static_assets.model_dump(
                mode="json"
            ),
            local_mail=self.protected.local_mail.model_dump(mode="json"),
        )
        return {
            "object_id": "shopping_order_eta:" + self.fixture.order_number,
            "values": {"estimated_delivery_date": self.fixture.date},
            "source_state": source,
        }
