"""Preserved four-check semantics, unknowns and exact selected-evidence bindings."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.evaluators.shopping_admin.product_description import (
    ProductDescriptionEvaluator,
    CHECKS,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    ProductDescriptionEvidence,
)
from lab_generate_skill.task_families.html_text import plain_text
from product_evaluator_fixtures import EvalCase
from test_slurm_commands import guard
import trace_fixtures


def test_original_update_success_and_no_target_extra_field_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = EvalCase(tmp_path, monkeypatch)
    row = json.loads(c.after.target_record_json or "{}")
    row["price"] = "999.0"  # Legacy protects other records, not every target field.
    c.after = c.after.model_copy(update={"target_record_json": json.dumps(row)})
    selection = c.selection.model_copy(update={"after": c.site_pair(c.after, "after")})
    result = ProductDescriptionEvaluator(selection).evaluate(
        c.contract, c.store, guard()
    )
    assert result.status == "success" and result.reward == 1
    assert tuple(x.name for x in result.checks) == CHECKS


@pytest.mark.parametrize(
    "fault",
    ["description", "other_digest", "other_count", "login", "page_error", "host"],
)
def test_complete_negative_facts_are_valid_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = EvalCase(tmp_path, monkeypatch)
    if fault == "description":
        row = json.loads(c.after.target_record_json or "{}")
        row["description"] = "Wrong"
        c.after = c.after.model_copy(update={"target_record_json": json.dumps(row)})
    elif fault == "other_digest":
        c.after = c.after.model_copy(update={"other_products_sha256": "f" * 64})
    elif fault == "other_count":
        c.after = c.after.model_copy(update={"other_product_count": 3})
    elif fault == "host":
        c.health = c.health.model_copy(update={"url": "http://foreign.example/admin"})
    else:
        c.health = c.health.model_copy(update={fault: True})
    selection = c.selection.model_copy(
        update={"after": c.site_pair(c.after, "after"), "page": c.page_pair()}
    )
    result = ProductDescriptionEvaluator(selection).evaluate(
        c.contract, c.store, guard()
    )
    assert result.status == "failure" and result.reward == 0
    assert sum(x.status == "fail" for x in result.checks) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "before",
        "after",
        "page",
        "trace_ref",
        "absent_target",
        "runtime_error",
        "foreign_observation",
        "wrong_result",
        "different_source",
        "same_operation",
        "foreign_attempt",
        "bad_hash",
    ],
)
def test_missing_invalid_or_runtime_fault_never_becomes_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = EvalCase(tmp_path, monkeypatch)
    values: dict[str, Any] = {}
    if fault in ("before", "after", "page", "trace_ref"):
        values[fault] = None
    elif fault == "absent_target":
        values["after"] = c.site_pair(
            c.after.model_copy(update={"target_record_json": None}), "after"
        )
    elif fault == "runtime_error":
        values["trace_ref"] = c.put(
            trace_fixtures.fixture(c.store, outcomes=("failed",)).trace
        )
    elif fault == "foreign_observation":
        values["page"] = c.page_pair(observation_sha256="f" * 64)
    elif fault == "foreign_attempt":
        assert c.selection.after is not None
        intent = SiteCaptureIntent.model_validate_json(
            c.store.read(c.selection.after.intent_ref)
        )
        values["after"] = c.site_pair(
            c.after,
            "after",
            operation=intent.request.operation.model_copy(
                update={"attempt_id": "foreign"}
            ),
        )
    elif fault == "same_operation":
        values["after"] = c.site_pair(c.after, "before")
    elif fault == "different_source":
        values["after"] = c.site_pair(
            c.after, "after", private_input='{"different":true}'
        )
    else:
        assert c.selection.after is not None
        pair = c.selection.after
        if fault == "bad_hash":
            ref = pair.result_ref.model_copy(update={"sha256": "f" * 64})
        else:
            captured = SiteTaskResult.model_validate_json(c.store.read(pair.result_ref))
            ref = c.put(captured.model_copy(update={"request_sha256": "f" * 64}))
        values["after"] = pair.model_copy(update={"result_ref": ref})
    selection = ProductDescriptionEvidence.model_validate(
        {**c.selection.model_dump(), **values}
    )
    result = ProductDescriptionEvaluator(selection).evaluate(
        c.contract, c.store, guard()
    )
    assert result.status == "unknown" and result.reward is None


def test_wrong_contract_and_cancel_do_not_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = EvalCase(tmp_path, monkeypatch)
    evaluator = ProductDescriptionEvaluator(c.selection)
    with pytest.raises(ValueError):
        evaluator.requirements(
            c.contract.model_copy(
                update={
                    "requirements": c.contract.requirements.model_copy(
                        update={"facts": ()}
                    )
                }
            )
        )

    def stopped(*args: Any, **kwargs: Any) -> bytes:
        raise OperationStopped("CANCELLED", "evaluation")

    monkeypatch.setattr(c.store, "read", stopped)
    with pytest.raises(OperationStopped):
        evaluator.evaluate(c.contract, c.store, guard())


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        0,
        "<p>a</p><p>b</p>",
        "A &amp; B",
        "a<br>b",
        "a<script>hidden</script>b",
        "<style>hidden</style> shown",
        "\t中 文\n",
        "<div>abc",
        "one<br/>two",
    ],
)
def test_plain_text_exact_legacy_semantics(value: object) -> None:
    namespace: dict[str, Any] = {}
    path = Path(__file__).parent / "fixtures/admin-legacy-text-content.py.txt"
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    from lab_generate_skill.admin_text_content import plain_text as old_surface

    assert plain_text(value) == namespace["plain_text"](value) == old_surface(value)


@pytest.mark.parametrize(
    "change", ["none", "description", "other", "target_extra", "login", "error", "host"]
)
def test_four_judgments_match_frozen_original_update_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from urllib.parse import urlsplit
    from test_admin_description_inputs import FIXTURE

    c = EvalCase(tmp_path, monkeypatch)
    before = json.loads(c.before.target_record_json or "{}")
    after = json.loads(c.after.target_record_json or "{}")
    other_before = [
        {"entity_id": "1", "name": "Other"},
        {"entity_id": "2", "name": "Another"},
    ]
    other_after = list(other_before)
    if change == "description":
        after["description"] = "Wrong"
    if change == "other":
        other_after = [{"entity_id": "1", "name": "Changed"}, other_before[1]]
        c.after = c.after.model_copy(update={"other_products_sha256": "f" * 64})
    if change == "target_extra":
        after["price"] = "999.0"
    if change == "login":
        c.health = c.health.model_copy(update={"login": True})
    if change == "error":
        c.health = c.health.model_copy(update={"page_error": True})
    if change == "host":
        c.health = c.health.model_copy(update={"url": "http://foreign.example/admin"})
    c.after = c.after.model_copy(update={"target_record_json": json.dumps(after)})
    selection = c.selection.model_copy(
        update={"after": c.site_pair(c.after, "after"), "page": c.page_pair()}
    )
    result = ProductDescriptionEvaluator(selection).evaluate(
        c.contract, c.store, guard()
    )
    namespace: dict[str, Any] = {"__package__": "lab_generate_skill"}
    path = Path(__file__).parent / "fixtures/admin-legacy-contract-rules.py.txt"
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    binding = json.loads(FIXTURE.read_bytes())
    binding["site_netloc"] = urlsplit(c.public.start_url).netloc
    expected = namespace["checks"](
        binding,
        {"records": {"product": [*other_before, before]}},
        {"records": {"product": [*other_after, after]}},
        c.health.model_dump(),
        "",
    )
    assert set(expected) == set(CHECKS)
    assert {check.name: check.status == "pass" for check in result.checks} == expected
    assert result.reward == int(all(expected.values()))
