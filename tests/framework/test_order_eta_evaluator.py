"""Actual CAS/canonical source/trace links, exact valid negatives and unknowns."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.evaluators.shopping.order_eta import OrderEtaEvaluator
from lab_generate_skill.sites.shopping.evidence_schema import OrderEtaEvidence
from lab_generate_skill.sites.shopping.tasks.order_eta_state import NativeEtaFixture
from lab_generate_skill.sites.shopping.tasks.order_eta_validation import (
    validate_eta_initialization,
)
from lab_generate_skill.sites.shopping.query_state import QueryProtection
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.sites.shopping.tasks.order_eta_state import (
    OrderEtaExecutionInput,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.trace import TraceTurn
from shopping_evaluator_fixtures import EtaEvalCase
from shopping_task_fixtures import protection
from test_slurm_commands import guard


def test_original_source_actual_step_issued_answer_positive(tmp_path: Path) -> None:
    c = EtaEvalCase(tmp_path)
    result = OrderEtaEvaluator(c.selection).evaluate(c.contract, c.store, guard())
    assert (
        result.status == "success"
        and result.reward == 1
        and all(x.status == "pass" for x in result.checks)
    )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_answer",
        "no_answer",
        "message_error",
        "core",
        "history_time",
        "history_status",
        "login",
        "404",
        "host",
    ],
)
def test_complete_negative_facts_are_valid_failure(tmp_path: Path, fault: str) -> None:
    c = EtaEvalCase(tmp_path)
    if fault in ("wrong_answer", "no_answer", "message_error"):
        c.trace = c.trace_with_answer(
            (
                None
                if fault == "no_answer"
                else (
                    '{"estimated_delivery_date":"2023-02-04"}'
                    if fault == "wrong_answer"
                    else '{"estimated_delivery_date":"2023-02-03"}'
                )
            ),
            "original browser API error" if fault == "message_error" else "",
        )
    elif fault == "core":
        c.after = c.after.model_copy(
            update={
                "protected": c.after.protected.model_copy(
                    update={"core_fingerprint": "d" * 64}
                )
            }
        )
    elif fault in ("history_time", "history_status"):
        raw = c.after.fixture.model_dump(mode="json")
        key = "created_at" if fault == "history_time" else "status"
        raw["history_note"][key] = (
            "2020-01-02 00:00:00" if fault == "history_time" else "processing"
        )
        raw["native_history_rows"] = [raw["history_note"]]
        changed = NativeEtaFixture.model_validate_json(json.dumps(raw))
        c.after = c.after.model_copy(update={"fixture": changed})
        # The initialization assertion remains strict; a later complete captured
        # mutation is retained and judged failure, matching the original reader.
        original = c.before.protected.model_copy(
            update={
                "protection": QueryProtection.model_validate_json(
                    json.dumps(protection(False))
                )
            }
        )
        with pytest.raises(ValueError, match="history time/status"):
            validate_eta_initialization(c.spec, original, c.after)
    elif fault == "login":
        c.health = c.health.model_copy(update={"login_page": True})
    elif fault == "404":
        c.health = c.health.model_copy(update={"http_status": 404, "error_page": True})
    else:
        c.health = c.health.model_copy(update={"url": "http://127.0.0.1:19001/"})
    selected = c.selection.model_copy(
        update={
            "after": c.site_pair(c.after, "after"),
            "trace_ref": c.put(c.trace),
            "page": c.page_pair(),
        }
    )
    result = OrderEtaEvaluator(selected).evaluate(c.contract, c.store, guard())
    assert result.status == "failure" and result.reward == 0
    if fault == "message_error":
        assert (
            next(x for x in result.checks if x.name == "answer_schema").status == "fail"
        )


@pytest.mark.parametrize(
    "fault",
    [
        "before",
        "after",
        "page",
        "trace_ref",
        "500",
        "missing_http",
        "bad_result",
        "same_operation",
        "foreign_observation",
        "foreign_attempt",
        "private_input",
        "missing_return",
        "wrong_actual_return",
    ],
)
def test_missing_corrupt_or_foreign_evidence_remains_unknown(
    tmp_path: Path, fault: str
) -> None:
    c = EtaEvalCase(tmp_path)
    changes: dict[str, Any] = {}
    if fault in ("before", "after", "page", "trace_ref"):
        changes[fault] = None
    elif fault in ("500", "missing_http"):
        c.health = c.health.model_copy(
            update=(
                {"http_status": 500, "error_page": True}
                if fault == "500"
                else {"http_status": None, "status_source": "unavailable"}
            )
        )
        changes["page"] = c.page_pair()
    elif fault == "same_operation":
        changes["after"] = c.site_pair(c.after, "before")
    elif fault == "foreign_observation":
        changes["page"] = c.page_pair(observation_sha256="f" * 64)
    elif fault == "foreign_attempt":
        assert c.selection.after is not None
        intent = SiteCaptureIntent.model_validate_json(
            c.store.read(c.selection.after.intent_ref, control=guard())
        )
        changes["after"] = c.site_pair(
            c.after,
            "after",
            operation=intent.request.operation.model_copy(
                update={"attempt_id": "other"}
            ),
        )
    elif fault == "private_input":
        changes["after"] = c.site_pair(
            c.after,
            "after",
            private_input=OrderEtaExecutionInput(
                spec=c.spec.model_copy(update={"recorded_date": "2023-02-04"})
            ).model_dump_json(),
        )
    elif fault == "bad_result":
        assert c.selection.after is not None
        captured_result = SiteTaskResult.model_validate_json(
            c.store.read(c.selection.after.result_ref, control=guard())
        )
        changes["after"] = c.selection.after.model_copy(
            update={
                "result_ref": c.put(
                    captured_result.model_copy(update={"request_sha256": "f" * 64})
                )
            }
        )
    else:
        turn = c.trace.turns[0]
        event = turn.interaction
        assert event is not None and event.result is not None
        ref = event.result.return_ref
        if fault == "missing_return":
            path = tmp_path / "blobs" / ref.sha256
            path.unlink()
        else:
            returned = BrowserReadout.model_validate_json(
                c.store.read(ref, control=guard())
            )
            returned = returned.model_copy(
                update={
                    "operation": returned.operation.model_copy(
                        update={"operation_id": "other"}
                    )
                }
            )
            step = event.result.model_copy(update={"return_ref": c.put(returned)})
            event = event.model_copy(update={"result": step})
            c.trace = c.trace.model_copy(
                update={
                    "turns": (
                        TraceTurn(
                            generation=turn.generation,
                            decision=turn.decision,
                            interaction=event,
                        ),
                    )
                }
            )
            changes["trace_ref"] = c.put(c.trace)
    selected = OrderEtaEvidence.model_validate({**c.selection.model_dump(), **changes})
    result = OrderEtaEvaluator(selected).evaluate(c.contract, c.store, guard())
    assert result.status == "unknown" and result.reward is None
