"""One pure initialization rule shared by the native producer and record reader."""

from .order_eta_spec import OrderEtaSpec
from .order_eta_state import OrderEtaState
from ..query_state import QueryProtectedState


def validate_eta_initialization(
    spec: OrderEtaSpec, original: QueryProtectedState, measured: OrderEtaState
) -> None:
    measured.check(spec)
    fixture = measured.fixture
    if (
        not fixture.order.get("created_at")
        or not fixture.order.get("status")
        or (fixture.history_note.get("created_at"), fixture.history_note.get("status"))
        != (fixture.order["created_at"], fixture.order["status"])
    ):
        raise ValueError("Native initialization changed original history time/status")
    actual = measured.protected
    for name, table in original.protection.tables.items():
        current = actual.protection.tables[name]
        if name == "sales_order_status_history":
            if current.rows != table.rows + 1 or (
                current.primary_key,
                current.columns,
                current.ignored_columns,
            ) != (table.primary_key, table.columns, table.ignored_columns):
                raise ValueError(
                    "Native initialization did not add exactly one history row"
                )
        elif current != table:
            raise ValueError("Native initialization changed another protected table")
    if (actual.core_fingerprint, actual.local_mail, actual.native_static_assets) != (
        original.core_fingerprint,
        original.local_mail,
        original.native_static_assets,
    ):
        raise ValueError("Native initialization changed protected core/mail/assets")
