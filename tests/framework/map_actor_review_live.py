"""Later process: original actual Map Actor, full native files, Reset and closures."""

from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from source_actor_projection import original_source_projection

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.evaluation import Evaluation, EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.sites.map.evidence_schema import (
    MapOverlayEvidence,
    MapNavigationEvidence,
)
from lab_generate_skill.domain.map_navigation_terminal import (
    MapNavigationTerminalSelection,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from generator_engine_live import verify_source
from source_actor_review import review_actor, read_fact
from source_review_records import ReadOnlyEvidence, review_resource, review_state
from map_closed_review_access import ClosedMapReviewAccess
from map_closed_review_evaluation import ClosedMapEvaluation
from test_resource_journal import NoCancellation


def test_independent_actual_map_actor_attempt() -> None:
    review_actual_map_attempt(Path(os.environ["LAB_MAP_ACTOR_ATTEMPT_ROOT"]))


def review_actual_map_attempt(root: Path) -> None:
    actor_path = root / "map-actor-native/facts.json"
    original_actor = actor_path.read_bytes()
    actor = json.loads(original_actor)
    site_path = Path(actor["site_facts_path"])
    if not site_path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError("Map site facts left the original attempt root")
    original_site = site_path.read_bytes()
    site = json.loads(original_site)
    project = Path(__file__).resolve().parents[2]
    verify_source(Path(actor["software_receipt"]), source_root=project)
    store = ReadOnlyEvidence(root / "map-actor-native/resource/evidence")
    controls = OperationGuards(SystemClock(), NoCancellation())
    spec = SiteResourceSpec.model_validate_json(json.dumps(site["configuration"]))
    browser = BrowserResourceSpec.model_validate_json(
        json.dumps(site["prepared_browser"]["browser_spec"])
    )
    owner = spec.token.owner
    op = OperationContext(
        operation_id="independent-map-closed-review",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        attempt_id=browser.token.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
        mode="cleanup",
        parent_operation_id="actual-map-actor",
    )
    control = controls.bind(op)
    access = ClosedMapReviewAccess(
        spec,
        browser,
        ResourceRecord.model_validate_json(json.dumps(site["resource_record"])),
        ResourceRecord.model_validate_json(
            json.dumps(site["prepared_browser"]["browser_record"])
        ),
        store,
        control,
    )
    data = actor["actor"]
    request = read_fact(
        store,
        EvidenceRef.model_validate(data["planned_actor_request_ref"]),
        ActorRunRequest,
        control,
    )
    snapshot = read_fact(
        store,
        EvidenceRef.model_validate(data["trace_snapshot_ref"]),
        TraceSnapshot,
        control,
    )
    trace = read_fact(
        store, EvidenceRef.model_validate(data["trace_ref"]), InteractionTrace, control
    )
    assert snapshot.project().sealed == trace
    executions = tuple(
        read_fact(store, EvidenceRef.model_validate(v), LocalActorExecution, control)
        for v in data["executions"]
    )
    summary = review_actor(
        request,
        snapshot,
        executions,
        store,
        controls,
        op,
        project=build_actor_projection(
            original_source_projection(request, snapshot.plan, store, controls.bind(op))
        ),
        context=(
            closed_actor_context(
                request,
                executions,
                store,
                EvidenceObservations(store, controls),
                control=control,
            )
            if request.schema_version == "actor-run-request/2"
            else None
        ),
    )
    resource = review_resource(
        actor["resource_record"], request.model_allocation, store, control
    )
    actor_record = ResourceRecord.model_validate_json(
        json.dumps(actor["resource_record"])
    )
    assert request.browser_allocation == browser.token
    for execution in executions:
        assert execution.call.binding.acquired_ref == actor_record.events[2].evidence[0]
        assert (
            execution.guard.model_dump(mode="json")
            == resource["acquired"]["owner_guard"]
        )
    initial, reset = review_state(site, store, control)
    assert initial.prepared.scope == request.scope == trace.scope
    assert (
        initial.public_task == request.task
        and initial.observation_ref == trace.initial_observation_ref
    )
    assert reset.plan.attempt_allocations == (browser.token,)
    review = ClosedMapEvaluation(
        access,
        initial,
        SiteResourceStarted.model_validate_json(json.dumps(site["started"])),
        store,
        controls,
        op,
    )
    judgment = data["judgment"]
    selected: MapOverlayEvidence | MapNavigationEvidence
    if request.task.identity.family == "navigation_page_identity":
        selected = read_fact(
            store,
            EvidenceRef.model_validate(judgment["selected_evidence_ref"]),
            MapNavigationEvidence,
            control,
        )
        assert selected.terminal_ref is not None
        terminal_selection = read_fact(
            store, selected.terminal_ref, MapNavigationTerminalSelection, control
        )
        assert terminal_selection.trace_ref == EvidenceRef.model_validate(
            data["trace_ref"]
        )
        assert terminal_selection.trace_snapshot_ref == EvidenceRef.model_validate(
            data["trace_snapshot_ref"]
        )
    else:
        selected = read_fact(
            store,
            EvidenceRef.model_validate(judgment["selected_evidence_ref"]),
            MapOverlayEvidence,
            control,
        )
        assert selected.trace_ref == EvidenceRef.model_validate(data["trace_ref"])
        assert selected.trace_snapshot_ref == EvidenceRef.model_validate(
            data["trace_snapshot_ref"]
        )
    contract = read_fact(
        store,
        EvidenceRef.model_validate(judgment["contract_ref"]),
        EvaluationContract,
        control,
    )
    saved = read_fact(
        store,
        EvidenceRef.model_validate(judgment["evaluation_ref"]),
        Evaluation,
        control,
    )
    assert contract.identity == request.task.identity
    assert contract.task_contract_ref == initial.preparation.task_binding_ref
    assert (
        contract.public_task_ref == initial.binding.public_task_ref
        and contract.completion_spec_ref == initial.binding.private_spec_ref
    )
    assert review.evaluator(selected).evaluate(contract, store, control) == saved
    checked = review.reset(
        EvidenceRef.model_validate(site["qualified_source"]["reset_selection_ref"]),
        control,
    )
    assert (
        checked.task,
        checked.environment,
        checked.health,
        checked.plan,
        checked.closures,
    ) == (
        reset.task.checks,
        reset.environment.checks,
        reset.health.checks,
        reset.plan,
        reset.closures,
    )
    assert (
        saved.status in ("success", "failure")
        and not data.get("errors")
        and actor["paid_calls"] == 0
    )
    assert (
        actor["local_staging_removed_after_step_closure"]
        and site["private_root_removed"]
        and not Path(site["private_root"]).exists()
    )
    assert (
        actor_path.read_bytes() == original_actor
        and site_path.read_bytes() == original_site
    )
    verify_source(Path(actor["software_receipt"]), source_root=project)
    report = dict(
        engineering_only=True,
        formal_source_admission=False,
        business_accepted=True,
        original_job_root=str(root),
        independent_process=os.getpid(),
        read_only=True,
        actor_facts_sha256=hashlib.sha256(original_actor).hexdigest(),
        site_facts_sha256=hashlib.sha256(original_site).hexdigest(),
        actor=summary,
        evaluation=saved.model_dump(mode="json"),
        baseline="ready",
        reset="safe",
        resources="original_actor_browser_site_closed",
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "map-actor-independent-review.json"
    ).write_text(json.dumps(report, indent=2) + "\n")
