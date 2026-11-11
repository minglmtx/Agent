"""One registered entry: shared Actor -> complete judgment -> independent reset.

CAS, journals, wire, collectors and evaluators are real. Model, native services,
Page and kernel authority are explicit doubles; no real Map Actor claim.
"""

from datetime import datetime, timezone
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.bootstrap.map_overlay_evaluation import map_overlay_evaluator
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.evaluators.map.native_overlay import REQUIREMENTS
from lab_generate_skill.sites.map.evidence_schema import (
    MapCapturePair,
    MapOverlayEvidence,
)
from lab_generate_skill.sites.map.page_capture import PAGE_HEALTH_PROGRAM
from map_registered_worker_fixtures import RegisteredMapCase
from map_initial_records_fixtures import initial_prepared
from map_terminal_fixtures import select_original, TerminalCase
from map_qualification_fixtures import qualified, restore
from map_overlay_capture_fixtures import full_surface_fixture
from map_actor_trace_fixtures import execute_actor
from map_ready_baseline_fixtures import ready_baseline
from map_evaluation_boundary_fixtures import negative_records
from map_evaluation_capture_fixtures import capture_database
from map_terminal_request_fixtures import Requests
from preparation_record_fixtures import put
from test_site_capture import Authority
from test_map_page_health import health
from test_map_browser_collection import capture
from test_map_qualified_combination import StateAuthority
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
from map_prepared_records_fixtures import PreparedMapCase


@pytest.mark.parametrize("mode", ["no-request", "native", "batch"])
def test_shared_actor_terminal_evaluation_readonly_review_and_safe_reset(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    original, store = registered_map, registered_map.resource.evidence
    proof = select_original(original)
    full_surface_fixture(monkeypatch)
    requests = Requests(monkeypatch, mode) if mode != "no-request" else None
    with qualified(original, monkeypatch, browser=True) as q:
        assert q.browser is not None
        assert isinstance(q.preparation, PreparedMapCase)
        with initial_prepared(
            original, monkeypatch, q.live, q.preparation, browser_case=q.browser
        ) as i:
            b = i.browser
            ready_baseline(original, i)
            trace_ref, journal_ref, trace, snapshot = execute_actor(original, i)
            assert (
                b.engine is not None
                and b.engine.last_readout is not None
                and b.engine.last_readout.observation.sequence == 1
            )
            if requests is not None:
                requests(i)
            recorder, request = capture(b, i.session)
            terminal_result = recorder.capture(request, control=guard(60))
            assert recorder.intent_ref is not None
            selection = MapTerminalSelection(
                initial=i.selection,
                capture_intent_ref=recorder.intent_ref,
                capture_result_ref=terminal_result,
                original_reference_ref=proof,
            )
            terminal_ref = put(store, selection)
            c = TerminalCase(
                original,
                i,
                selection,
                terminal_ref,
                i.operation.model_copy(update={"operation_id": "terminal-judgment"}),
            )
            evaluate = b.page.evaluate

            def page_read(program: str, args: Any = None) -> Any:
                return (
                    health(b.page.url)
                    if program == PAGE_HEALTH_PROGRAM
                    else evaluate(program, args)
                )

            monkeypatch.setattr(b.page, "evaluate", page_read)
            recorder, request = capture(b, i.session)
            request = request.model_copy(
                update={
                    "collector_id": "map-page-health",
                    "operation": request.operation.model_copy(
                        update={"operation_id": "selected-final-health"}
                    ),
                }
            )
            health_result = recorder.capture(request, control=guard())
            assert recorder.intent_ref is not None
            page = MapCapturePair(
                intent_ref=recorder.intent_ref, result_ref=health_result
            )
            refs: tuple[MapCapturePair, ...] = ()
            queries: list[tuple[str, ...]] = []
            if requests is not None:
                pair, queries = capture_database(c, monkeypatch)
                refs = (pair,)
        browser_read = b.resource.op.cleanup(
            "selected-closed-browser-read", now=datetime.now(timezone.utc), seconds=30
        )
        record = b.resource.journal.read(b.resource.spec.token, browser_read)
        assert record.state == "closed"
        closure = ClosureReceipt.model_validate_json(
            json.dumps(
                json.loads(store.read(record.events[-1].evidence[0]))["details"][
                    "closure"
                ]
            )
        )
        closure_ref = put(store, closure)
        original.observer = "worker"
        inspection = original.request("inspect", "complete-final-guard")
        inspection = inspection.model_copy(
            update={
                "operation": inspection.operation.model_copy(
                    update={"parent_operation_id": closure.operation_id}
                )
            }
        )
        recorder_state = RecordedSiteCapture(q.live.capture, store, Authority(store))
        result = recorder_state.capture(
            SiteCaptureRequest(
                inspection=inspection,
                collector_id="map-overlay-state",
                collector_version="1",
            ),
            control=guard(60),
        )
        assert recorder_state.intent_ref is not None
        chosen = MapOverlayEvidence(
            environment_ref=q.environment_ref,
            terminal_ref=terminal_ref,
            page=page,
            references=refs,
            final_guard=MapCapturePair(
                intent_ref=recorder_state.intent_ref, result_ref=result
            ),
            browser_closure_ref=closure_ref,
            trace_ref=trace_ref,
            trace_snapshot_ref=journal_ref,
        )
        binding = TaskBinding.model_validate_json(store.read(original.binding))
        contract = EvaluationContract(
            identity=original.scope.task,
            attempt_id=original.scope.attempt_id,
            task_contract_ref=original.binding,
            public_task_ref=binding.public_task_ref,
            completion_spec_ref=binding.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )
        original.observer = b.participant = "controller"

        reviews = 0

        def judge(selected: MapOverlayEvidence = chosen) -> Evaluation:
            nonlocal reviews
            reviews += 1
            review_op = c.operation.cleanup(
                f"selected-readonly-review-{reviews}",
                now=datetime.now(timezone.utc),
                seconds=120,
            )
            evaluator = map_overlay_evaluator(
                selected,
                q.preparation.records,
                original.resource.spec,
                q.live.site,
                review_op,
            )
            return evaluator.evaluate(
                contract, store, b.resource.controls.bind(review_op)
            )

        before = (len(original.case.commands.calls), len(b.calls), len(queries))
        judged = judge()
        assert judged.status == "failure", judged.model_dump_json()
        assert judged.reward == 0 and any(
            check.name == "actual_local_response_valid" and check.status == "fail"
            for check in judged.checks
        )
        assert judge() == judged  # Independent re-read, no query/step/restore effects.
        assert before == (len(original.case.commands.calls), len(b.calls), len(queries))
        assert len(queries) == int(mode != "no-request")
        with pytest.raises(OperationStopped):
            map_overlay_evaluator(
                chosen,
                q.preparation.records,
                original.resource.spec,
                q.live.site,
                c.operation,
            ).evaluate(contract, store, guard(-1))
        if mode == "no-request":
            negative_records(store, chosen, trace, snapshot, judge)
            for field in (
                "environment_ref",
                "terminal_ref",
                "page",
                "references",
                "final_guard",
                "browser_closure_ref",
                "trace_ref",
                "trace_snapshot_ref",
            ):
                unknown = judge(chosen.model_copy(update={field: None}))
                assert unknown.status == "unknown" and unknown.reward is None
            changed = snapshot.model_copy(update={"events": snapshot.events[:-1]})
            assert (
                judge(
                    chosen.model_copy(
                        update={"trace_snapshot_ref": put(store, changed)}
                    )
                ).status
                == "unknown"
            )
            assert (
                judge(
                    chosen.model_copy(
                        update={
                            "browser_closure_ref": put(
                                store,
                                closure.model_copy(update={"status": "unconfirmed"}),
                            )
                        }
                    )
                ).status
                == "unknown"
            )
            assert before == (
                len(original.case.commands.calls),
                len(b.calls),
                len(queries),
            )
        selected_reset = restore(q, closure_refs=(closure_ref,), forced=mode == "batch")
        reset_op = q.preparation.request.operation.cleanup(
            "selected-reset-facts", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": q.plan.environment_recovery_ref})
        reset_inputs = q.qualifications.publish_reset_facts(
            put(store, selected_reset), reset_op
        )
        final_op = reset_op.model_copy(
            update={"operation_id": "selected-reset-summary"}
        )
        reset = assemble_reset(reset_inputs, final_op)
        states = EvidenceStateRecords(
            store, original.resource.controls, StateAuthority(original)
        )
        reset_ref = states.publish_reset(reset, final_op)
        assert (
            states.load_reset(reset_ref, final_op) == reset and reset.status == "safe"
        )
        original.observer = b.participant = "controller"
        after_reset = (len(original.case.commands.calls), len(b.calls), len(queries))
        assert judge() == judged
        assert after_reset == (
            len(original.case.commands.calls),
            len(b.calls),
            len(queries),
        )
    final_read = original.resource.op.cleanup(
        "selected-closed-site-read", now=datetime.now(timezone.utc), seconds=30
    )
    assert (
        original.resource.journal.read(original.resource.spec.token, final_read).state
        == "closed"
    )
    original.observer = b.participant = "controller"
    assert judge() == judged and len(queries) == int(mode != "no-request")
