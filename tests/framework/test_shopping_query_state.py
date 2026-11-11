"""Original31-table scope, native ownership/visibility and reference semantics."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.sites.shopping.query_state import QueryProtection, LocalMail
from lab_generate_skill.sites.shopping.tasks.order_eta_state import NativeEtaFixture
from shopping_task_fixtures import protection, native_fixture


def test_complete_original_query_scope_and_native_order_reference() -> None:
    state = QueryProtection.model_validate_json(json.dumps(protection()))
    assert len(state.tables) == 31 and not any(
        x.ignored_columns for x in state.tables.values()
    )
    fixture = NativeEtaFixture.model_validate_json(json.dumps(native_fixture()))
    assert fixture.order_number == "000000148" and fixture.date == "2023-02-03"


@pytest.mark.parametrize(
    "fault",
    [
        "missing_table",
        "extra_table",
        "ignored",
        "duplicate_key",
        "missing_column",
        "negative_rows",
        "bad_digest",
        "budget",
    ],
)
def test_incomplete_or_changed_query_scope_rejected(fault: str) -> None:
    value = protection()
    table = value["tables"]["sales_order"]
    if fault == "missing_table":
        value["tables"].pop("sales_order")
    elif fault == "extra_table":
        value["tables"]["unrelated"] = table
    elif fault == "ignored":
        table["ignored_columns"] = ["updated_at"]
    elif fault == "duplicate_key":
        table["primary_key"] = ["id", "id"]
    elif fault == "missing_column":
        table["primary_key"] = ["absent"]
    elif fault == "negative_rows":
        table["rows"] = -1
    elif fault == "bad_digest":
        table["sha256"] = "bad"
    else:
        value["statement_budget_seconds"] = 21
    with pytest.raises(ValueError):
        QueryProtection.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "fault",
    [
        "order",
        "customer",
        "number",
        "date",
        "notified",
        "invisible",
        "created_at",
        "source",
        "history_missing",
        "nan",
    ],
)
def test_original_native_fixture_wrong_identity_or_incomplete_evidence_rejected(
    fault: str,
) -> None:
    value = native_fixture()
    if fault == "order":
        value["order"]["entity_id"] = "99"
    elif fault == "customer":
        value["order"]["customer_id"] = "99"
    elif fault == "number":
        value["order_number"] = 148
    elif fault == "date":
        value["date"] = "2023-02-30"
    elif fault == "notified":
        value["history_note"]["is_customer_notified"] = "1"
    elif fault == "invisible":
        value["history_note"]["is_visible_on_front"] = "0"
    elif fault == "created_at":
        value["history_note"].pop("created_at")
    elif fault == "source":
        value["source_hashes"] = {}
    elif fault == "history_missing":
        value["native_history_rows"] = []
    else:
        value["order"]["extra"] = float("nan")
    with pytest.raises(ValueError):
        NativeEtaFixture.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "fault", ["outside", "duplicate", "not_sorted", "oversized", "external"]
)
def test_local_mail_metadata_is_complete_private_and_local(fault: str) -> None:
    row = {"file": "a.eml", "bytes": 1, "sha256": "a" * 64}
    value = {
        "backend": "local_sendmail_capture_v1",
        "messages": [row],
        "external_delivery": False,
    }
    if fault == "outside":
        row["file"] = "../outside"
    elif fault == "duplicate":
        value["messages"] = [row, row]
    elif fault == "not_sorted":
        value["messages"] = [{**row, "file": "z.eml"}, row]
    elif fault == "oversized":
        row["bytes"] = 5000001
    else:
        value["external_delivery"] = True
    with pytest.raises(ValueError):
        LocalMail.model_validate_json(json.dumps(value))
