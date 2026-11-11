"""Derived negative records never alter the original accepted execution or files."""

from collections.abc import Callable
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.actor_run import ActorStop
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import TraceSealed
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.browser_capture import BrowserCaptureResult
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.sites.map.page_health import MapPageHealth
from lab_generate_skill.sites.map.evidence_schema import MapOverlayEvidence
from evidence_control_fixtures import EvidenceFixtureStore
from preparation_record_fixtures import put


def negative_records(
    store: EvidenceFixtureStore,
    selected: MapOverlayEvidence,
    trace: InteractionTrace,
    snapshot: TraceSnapshot,
    judge: Callable[[MapOverlayEvidence], Evaluation],
) -> None:
    assert (
        selected.page is not None
        and selected.final_guard is not None
        and selected.browser_closure_ref is not None
    )
    page_result = BrowserCaptureResult.model_validate_json(
        store.read(selected.page.result_ref)
    )
    page = MapPageHealth.model_validate_json(page_result.private_result)
    other = page.model_copy(
        update={
            "url": "http://127.0.0.1:9999/other",
            "sampled_url": "http://127.0.0.1:9999/other",
        }
    )
    page_ref = put(
        store,
        page_result.model_copy(update={"private_result": other.model_dump_json()}),
    )
    bad_page = selected.model_copy(
        update={"page": selected.page.model_copy(update={"result_ref": page_ref})}
    )
    assert judge(bad_page).status == "unknown"
    closure = ClosureReceipt.model_validate_json(
        store.read(selected.browser_closure_ref)
    )
    assert (
        judge(
            selected.model_copy(
                update={
                    "browser_closure_ref": put(
                        store,
                        closure.model_copy(update={"operation_id": "different-close"}),
                    )
                }
            )
        ).status
        == "unknown"
    )
    intent = SiteCaptureIntent.model_validate_json(
        store.read(selected.final_guard.intent_ref)
    )
    wrong = intent.model_copy(update={"configuration_sha256": "f" * 64})
    assert (
        judge(
            selected.model_copy(
                update={
                    "final_guard": selected.final_guard.model_copy(
                        update={"intent_ref": put(store, wrong)}
                    )
                }
            )
        ).status
        == "unknown"
    )
    run = RunPlan.model_validate_json(store.read(snapshot.plan.binding.run.plan_ref))
    run = run.model_copy(
        update={
            "resources": run.resources.model_copy(
                update={"max_actor_generations_per_attempt": 2}
            )
        }
    )
    wrong_plan = snapshot.plan.model_copy(
        update={
            "binding": snapshot.plan.binding.model_copy(
                update={
                    "run": snapshot.plan.binding.run.model_copy(
                        update={"plan_ref": put(store, run)}
                    )
                }
            )
        }
    )
    wrong_snapshot = snapshot.model_copy(update={"plan": wrong_plan})
    assert (
        judge(
            selected.model_copy(
                update={"trace_snapshot_ref": put(store, wrong_snapshot)}
            )
        ).status
        == "unknown"
    )
    stop = ActorStop.model_validate_json(store.read(trace.stop_evidence_ref))
    for reason in ("cancelled", "error"):
        stop_ref = put(store, stop.model_copy(update={"reason": reason}))
        seal = TraceSealed.model_validate(
            snapshot.events[-1].model_copy(
                update={"stop_reason": reason, "stop_evidence_ref": stop_ref}
            )
        )
        derived = TraceSnapshot.model_validate(
            snapshot.model_copy(update={"events": (*snapshot.events[:-1], seal)})
        )
        derived_trace = derived.project().sealed
        assert derived_trace is not None
        result = judge(
            selected.model_copy(
                update={
                    "trace_ref": put(store, derived_trace),
                    "trace_snapshot_ref": put(store, derived),
                }
            )
        )
        assert (
            result.status == "unknown"
            and result.reward is None
            and result.reason_code == "INCOMPLETE_ACTOR_EXECUTION"
        )
