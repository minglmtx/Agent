"""Decisions match exact frozen original string-query and complete integrity."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.task_families.recorded_order_eta import decide_eta, CHECKS


@pytest.mark.parametrize(
    "case",
    [
        "positive",
        "wrong",
        "none",
        "extra",
        "missing",
        "duplicate",
        "scalar",
        "number",
        "whitespace",
        "changed_reference",
        "changed_core",
        "404",
        "login",
        "host",
        "500",
        "unknown_http",
    ],
)
def test_original_selected_rules_and_complete_reference_semantics(case: str) -> None:
    namespace: dict[str, Any] = {}
    path = Path(__file__).parent / "fixtures/shopping-eta-legacy-query-rules.py.txt"
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    before: dict[str, Any] = {
        "object_id": "shopping_order_eta:000000148",
        "values": {"estimated_delivery_date": "2023-02-03"},
        "source_state": {"protected": "original"},
    }
    after = json.loads(json.dumps(before))
    core = "c" * 64
    after_core = core
    page: dict[str, Any] = {
        "url": "http://127.0.0.1:12001/customer/account/",
        "http_status": 200,
        "login_page": False,
        "error_page": False,
    }
    answer: str | None = '{"estimated_delivery_date":"2023-02-03"}'
    if case == "wrong":
        answer = '{"estimated_delivery_date":"2023-02-04"}'
    elif case == "none":
        answer = None
    elif case == "extra":
        answer = '{"estimated_delivery_date":"2023-02-03","extra":"x"}'
    elif case == "missing":
        answer = "{}"
    elif case == "duplicate":
        answer = '{"estimated_delivery_date":"2023-02-03","estimated_delivery_date":"2023-02-03"}'
    elif case == "scalar":
        answer = '"2023-02-03"'
    elif case == "number":
        answer = '{"estimated_delivery_date":20230203}'
    elif case == "whitespace":
        answer = '{"estimated_delivery_date":" 2023-02-03 "}'
    elif case == "changed_reference":
        after["source_state"]["protected"] = "changed"
    elif case == "changed_core":
        after_core = "d" * 64
    elif case == "404":
        page.update(http_status=404, error_page=True)
    elif case == "login":
        page["login_page"] = True
    elif case == "host":
        page["url"] = "http://127.0.0.1:12002/customer/account/"
    elif case == "500":
        page.update(http_status=500, error_page=True)
    elif case == "unknown_http":
        page["http_status"] = None
    contract = {"query": {"fields": {"estimated_delivery_date": "string"}}}
    old = namespace["evaluate_query"](
        contract, page, answer, before, after, site_origin="http://127.0.0.1:12001/"
    )
    integrity = before == after and core == after_core
    old["checks"]["complete_native_reference_unchanged"] = integrity
    if old["status"] != "unknown" and not integrity:
        old.update(status="failure", reward=0.0)
    result = decide_eta(
        before=before,
        after=after,
        before_core=core,
        after_core=after_core,
        page_url=page["url"],
        http_status=page["http_status"],
        login_page=page["login_page"],
        error_page=page["error_page"],
        site_origin="http://127.0.0.1:12001/",
        answer=answer,
    )
    assert (result.status, result.reward) == (old["status"], old["reward"])
    assert result.checks == tuple(old["checks"].get(name) for name in CHECKS)
