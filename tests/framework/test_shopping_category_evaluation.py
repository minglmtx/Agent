"""Original current Actor/producers to fixed category evaluator; no live grant."""

from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationState,
)
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from shopping_category_evaluation_fixtures import complete_case
from preparation_record_fixtures import put
from test_slurm_commands import guard
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("heading", ["Electronics", ""])
def test_original_current_actor_capture_and_guard_yield_success_or_valid_failure(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    heading: str,
) -> None:
    def consume(c: dict[str, Any]) -> None:
        evaluate = c["evaluator"]()
        result = evaluate.evaluate(c["contract"], c["store"], guard())
        assert result.status == ("success" if heading else "failure")
        assert result.reward == (1 if heading else 0)
        assert evaluate.evaluate(c["contract"], c["store"], guard()) == result
        c["preparation_authority"].denied = True
        with pytest.raises(PermissionError):
            evaluate.evaluate(c["contract"], c["store"], guard())
        c["preparation_authority"].denied = False

    complete_case(
        tmp_path,
        node_path,
        monkeypatch,
        (originals[0][0], originals[0][2]),
        consume,
        heading=heading,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "closure_missing",
        "closure_token",
        "terminal_ref",
        "page_configuration",
        "page_missing_status",
        "guard_parent",
        "guard_state",
        "trace_ref",
        "initial_checks_scope",
        "cancel",
        "run_release",
        "run_task_binding",
        "run_purpose",
    ],
)
def test_missing_or_changed_provenance_never_becomes_scored_category_result(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    def consume(c: dict[str, Any]) -> None:
        store, selected = c["store"], c["selected"]
        assert (
            c["evaluator"]().evaluate(c["contract"], store, guard()).status == "success"
        )
        if fault == "closure_missing":
            selected = selected.model_copy(update={"browser_closure_ref": None})
        elif fault == "closure_token":
            closure = c["closure"].model_copy(
                update={
                    "token": c["closure"].token.model_copy(
                        update={"allocation_id": "foreign-browser"}
                    )
                }
            )
            selected = selected.model_copy(
                update={"browser_closure_ref": put(store, closure)}
            )
        elif fault == "terminal_ref":
            selected = selected.model_copy(
                update={
                    "terminal_return_ref": selected.terminal_return_ref.model_copy(
                        update={"producer": "foreign-full-reference"}
                    )
                }
            )
        elif fault == "page_configuration":
            page_intent = BrowserCaptureIntent.model_validate_json(
                store.read(selected.page.intent_ref, guard())
            )
            selected = selected.model_copy(
                update={
                    "page": selected.page.model_copy(
                        update={
                            "intent_ref": put(
                                store,
                                page_intent.model_copy(
                                    update={"configuration_sha256": "0" * 64}
                                ),
                            )
                        }
                    )
                }
            )
        elif fault == "page_missing_status":
            page_result = BrowserCaptureResult.model_validate_json(
                store.read(selected.page.result_ref, guard())
            )
            raw = json.loads(page_result.private_result)
            raw["health"].update(http_status=None, status_source="unavailable")
            page_result = page_result.model_copy(
                update={"private_result": json.dumps(raw, separators=(",", ":"))}
            )
            selected = selected.model_copy(
                update={
                    "page": selected.page.model_copy(
                        update={"result_ref": put(store, page_result)}
                    )
                }
            )
        elif fault == "guard_parent":
            native_intent = SiteCaptureIntent.model_validate_json(
                store.read(selected.final_guard.intent_ref, guard())
            )
            request = native_intent.request.model_copy(
                update={
                    "inspection": native_intent.request.inspection.model_copy(
                        update={
                            "operation": native_intent.request.operation.model_copy(
                                update={"parent_operation_id": "foreign-close"}
                            )
                        }
                    )
                }
            )
            selected = selected.model_copy(
                update={
                    "final_guard": selected.final_guard.model_copy(
                        update={
                            "intent_ref": put(
                                store,
                                native_intent.model_copy(update={"request": request}),
                            )
                        }
                    )
                }
            )
        elif fault == "guard_state":
            native_result = SiteTaskResult.model_validate_json(
                store.read(selected.final_guard.result_ref, guard())
            )
            state = CategoryNavigationState.model_validate_json(
                native_result.private_result
            )
            state = state.model_copy(
                update={
                    "protected": state.protected.model_copy(
                        update={"core_fingerprint": "0" * 64}
                    )
                }
            )
            selected = selected.model_copy(
                update={
                    "final_guard": selected.final_guard.model_copy(
                        update={
                            "result_ref": put(
                                store,
                                native_result.model_copy(
                                    update={"private_result": state.model_dump_json()}
                                ),
                            )
                        }
                    )
                }
            )
        elif fault == "trace_ref":
            selected = selected.model_copy(
                update={
                    "trace_ref": selected.trace_ref.model_copy(
                        update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
                    )
                }
            )
        elif fault.startswith("run_"):
            from lab_generate_skill.domain.trace_journal import TraceSnapshot
            from lab_generate_skill.domain.run_plan import RunPlan
            from retrieval_fixtures import reference

            journal = TraceSnapshot.model_validate_json(
                store.read(selected.trace_snapshot_ref, guard())
            )
            original_run = journal.plan.binding.run
            run = RunPlan.model_validate_json(
                store.read(original_run.plan_ref, guard())
            )
            if fault == "run_release":
                run = run.model_copy(
                    update={
                        "release_ref": reference(
                            {"different_declared_release": True},
                            "release-manifest/1",
                            store=store,
                        )
                    }
                )
            elif fault == "run_task_binding":
                run = run.model_copy(
                    update={
                        "tasks": (
                            run.tasks[0].model_copy(
                                update={"registration_id": "foreign-registration"}
                            ),
                        )
                    }
                )
            else:
                run = run.model_copy(update={"purpose": "evaluation"})
            run = RunPlan.model_validate_json(run.model_dump_json())
            bound = original_run.model_copy(
                update={"plan_ref": put(store, run), "release_ref": run.release_ref}
            )
            plan = journal.plan.model_copy(
                update={
                    "binding": journal.plan.binding.model_copy(update={"run": bound})
                }
            )
            journal = TraceSnapshot.model_validate_json(
                journal.model_copy(update={"plan": plan}).model_dump_json()
            )
            assert journal.project().sealed == c["trace"]
            selected = selected.model_copy(
                update={"trace_snapshot_ref": put(store, journal)}
            )
        elif fault == "initial_checks_scope":
            from lab_generate_skill.domain.baseline import InitialStateChecks

            first = InitialStateChecks.model_validate_json(
                store.read(selected.initial_checks_ref, guard())
            )
            first = first.model_copy(
                update={
                    "scope": first.scope.model_copy(
                        update={"attempt_id": "foreign-attempt"}
                    )
                }
            )
            selected = selected.model_copy(
                update={"initial_checks_ref": put(store, first)}
            )
        else:

            class Cancelled:
                def checkpoint(self) -> float:
                    raise OperationStopped("CANCELLED", "category-evaluation")

                def wait(self, seconds: float) -> None:
                    self.checkpoint()

            with pytest.raises(OperationStopped):
                c["evaluator"]().evaluate(c["contract"], store, Cancelled())
            return
        selected = CategoryNavigationEvidence.model_validate(selected)
        verdict = c["evaluator"](selected).evaluate(c["contract"], store, guard())
        assert verdict.status == "unknown" and verdict.reward is None

    complete_case(
        tmp_path, node_path, monkeypatch, (originals[0][0], originals[0][2]), consume
    )


def test_preclose_proof_cannot_supply_missing_closure_or_native_guard(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    from lab_generate_skill.bootstrap.shopping_category_evaluation import (
        shopping_category_evidence_reader,
    )

    def consume(c: dict[str, Any]) -> None:
        partial = c["selected"].model_copy(
            update={"browser_closure_ref": None, "final_guard": None}
        )
        reader = shopping_category_evidence_reader(
            c["preparations"], c["c"].spec, c["live"].site, c["prepare"].operation
        )
        reader.verify_terminal(c["contract"], partial, c["store"], guard())
        verdict = c["evaluator"](partial).evaluate(c["contract"], c["store"], guard())
        assert verdict.status == "unknown" and verdict.reward is None
        c["preparation_authority"].denied = True
        with pytest.raises(PermissionError):
            reader.verify_terminal(c["contract"], partial, c["store"], guard())
        c["preparation_authority"].denied = False

    complete_case(
        tmp_path, node_path, monkeypatch, (originals[0][0], originals[0][2]), consume
    )
