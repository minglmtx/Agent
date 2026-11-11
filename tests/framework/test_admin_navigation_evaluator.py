"""Original four checks, exact active-page/trace binding and unknown preservation."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.evaluators.shopping_admin.navigation import (
    AdminNavigationEvaluator,
    CHECKS,
)
from admin_navigation_evaluator_fixtures import EvalCase
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


def test_original_four_checks_and_independent_readonly_recomputation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    c = EvalCase(tmp_path, monkeypatch, contracts)
    evaluator = AdminNavigationEvaluator(c.selected)
    before = set(tmp_path.iterdir())
    first = evaluator.evaluate(c.contract, c.store, guard())
    assert first == AdminNavigationEvaluator(c.selected).evaluate(
        c.contract, c.store, guard()
    )
    assert first.status == "success" and first.reward == 1
    assert tuple(check.name for check in first.checks) == CHECKS
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("fault", ["heading", "path", "host", "login", "page_error"])
def test_complete_negative_facts_remain_valid_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any, fault: str
) -> None:
    final = (
        "http://127.0.0.1:18080/not-target"
        if fault == "path"
        else (
            "http://foreign.example/admin" + contracts[0][0]["spec"]["target_path"]
            if fault == "host"
            else None
        )
    )
    c = EvalCase(tmp_path, monkeypatch, contracts, final_url=final)
    if fault == "heading":
        c.page = c.page.model_copy(update={"heading": "Wrong heading"})
    elif fault in ("login", "page_error"):
        c.page = c.page.model_copy(update={fault: True})
    intent, result = c.page_pair()
    selected = c.selected.model_copy(
        update={"page_intent_ref": intent, "page_result_ref": result}
    )
    value = AdminNavigationEvaluator(selected).evaluate(c.contract, c.store, guard())
    assert value.status == "failure" and value.reward == 0
    assert sum(check.status == "fail" for check in value.checks) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "trace_ref",
        "page_intent_ref",
        "page_result_ref",
        "scope",
        "observation",
        "collector",
        "configuration",
        "result_request",
        "active_page",
        "source",
        "runtime_error",
        "missing_blob",
    ],
)
def test_incomplete_or_foreign_evidence_never_becomes_zero_reward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any, fault: str
) -> None:
    c = EvalCase(tmp_path, monkeypatch, contracts)
    selected, contract = c.selected, c.contract
    assert selected.page_intent_ref is not None and selected.page_result_ref is not None
    if fault in ("trace_ref", "page_intent_ref", "page_result_ref"):
        selected = selected.model_copy(update={fault: None})
    elif fault == "scope":
        selected = selected.model_copy(
            update={
                "scope": selected.scope.model_copy(update={"context_id": "foreign"})
            }
        )
    elif fault in ("observation", "collector"):
        intent, result = c.page_pair(
            **(
                {"observation_sha256": "f" * 64}
                if fault == "observation"
                else {"collector_id": "wrong"}
            )
        )
        selected = selected.model_copy(
            update={"page_intent_ref": intent, "page_result_ref": result}
        )
    elif fault == "configuration":
        ref = selected.page_intent_ref
        assert ref is not None
        captured_intent = BrowserCaptureIntent.model_validate_json(c.store.read(ref))
        selected = selected.model_copy(
            update={
                "page_intent_ref": c.put(
                    captured_intent.model_copy(
                        update={"configuration_sha256": "f" * 64}
                    )
                )
            }
        )
    elif fault == "result_request":
        ref = selected.page_result_ref
        assert ref is not None
        captured_result = BrowserCaptureResult.model_validate_json(c.store.read(ref))
        selected = selected.model_copy(
            update={
                "page_result_ref": c.put(
                    captured_result.model_copy(update={"request_sha256": "f" * 64})
                )
            }
        )
    elif fault == "active_page":
        c.page = c.page.model_copy(update={"url": "http://127.0.0.1:18080/other"})
        intent, result = c.page_pair()
        selected = selected.model_copy(
            update={"page_intent_ref": intent, "page_result_ref": result}
        )
    elif fault == "source":
        contract = contract.model_copy(
            update={
                "completion_spec_ref": c.put(
                    c.spec.model_copy(update={"heading": "Different original"})
                )
            }
        )
    elif fault == "runtime_error":
        import trace_fixtures

        selected = selected.model_copy(
            update={
                "trace_ref": c.put(
                    trace_fixtures.fixture(c.store, outcomes=("failed",)).trace
                )
            }
        )
    else:
        (tmp_path / "blobs" / selected.browser_spec_ref.sha256).unlink()
    value = AdminNavigationEvaluator(selected).evaluate(contract, c.store, guard())
    assert value.status == "unknown" and value.reward is None


def test_cancellation_propagates_before_evidence_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    c = EvalCase(tmp_path, monkeypatch, contracts)

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "navigation-evaluation")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    monkeypatch.setattr(
        c.store,
        "read",
        lambda *args, **kwargs: pytest.fail("Cancelled evaluation read evidence"),
    )
    with pytest.raises(OperationStopped):
        AdminNavigationEvaluator(c.selected).evaluate(c.contract, c.store, Stopped())


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", None),
        ("browser_spec_ref", None),
        ("trace_ref", "text"),
        ("page_intent_ref", {}),
        ("page_result_ref", 1),
    ],
)
def test_illegal_evidence_selection_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    field: str,
    value: Any,
) -> None:
    from lab_generate_skill.sites.shopping_admin.evidence_schema import (
        AdminNavigationEvidence,
    )

    c = EvalCase(tmp_path, monkeypatch, contracts)
    with pytest.raises(ValueError):
        AdminNavigationEvidence.model_validate(
            {**c.selected.model_dump(), field: value}
        )
