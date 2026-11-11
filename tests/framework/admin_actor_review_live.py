"""Separate compute process, read-only whole engineering attempt review."""

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
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.evaluators.shopping_admin.product_description import (
    ProductDescriptionEvaluator,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    ProductDescriptionEvidence,
)
from lab_generate_skill.sites.shopping.evidence_schema import OrderEtaEvidence
from lab_generate_skill.evaluators.shopping.order_eta import OrderEtaEvaluator
from lab_generate_skill.runtime.lifecycle import OperationGuards
from generator_engine_live import verify_source
from source_actor_review import review_actor, read_fact
from source_review_records import ReadOnlyEvidence, review_resource, review_state
from test_resource_journal import NoCancellation


def test_independent_actual_admin_actor_attempt() -> None:
    review_actual_actor_attempt(
        Path(os.environ["LAB_ADMIN_ACTOR_ATTEMPT_ROOT"]), shopping=False
    )


def review_actual_actor_attempt(
    root: Path,
    *,
    shopping: bool = False,
    gitlab: bool = False,
    reddit: bool = False,
    execution_source_root: Path | None = None,
    expected_identity: TaskIdentity | None = None,
) -> None:
    if expected_identity is not None:
        expected_identity = TaskIdentity.model_validate(expected_identity)
    if sum((shopping, gitlab, reddit)) > 1:
        raise ValueError("Independent review must select one original site")
    label = (
        "reddit"
        if reddit
        else "gitlab" if gitlab else "shopping" if shopping else "admin"
    )
    actor_path, site_path = (
        root / (label + "-actor-native/facts.json"),
        root / "registered-site-actor_source.json",
    )
    original_actor, original_site = actor_path.read_bytes(), site_path.read_bytes()
    actor, site = json.loads(original_actor), json.loads(original_site)
    execution_source = (
        Path(__file__).resolve().parents[2]
        if execution_source_root is None
        else execution_source_root
    )
    verify_source(Path(actor["software_receipt"]), source_root=execution_source)
    store = ReadOnlyEvidence(root / (label + "-actor-native/resource/evidence"))
    controls = OperationGuards(SystemClock(), NoCancellation())
    op = OperationContext(
        operation_id="independent-admin-review",
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=90),
        mode="cleanup",
        parent_operation_id="actual-source-actor",
    )
    control = controls.bind(op)
    data = actor["actor"]
    request = read_fact(
        store,
        EvidenceRef.model_validate(data["planned_actor_request_ref"]),
        ActorRunRequest,
        control,
    )
    if expected_identity is not None and request.task.identity != expected_identity:
        raise OwnershipConflict("Independent review changed the selected task identity")
    op = op.model_copy(update={"attempt_id": request.scope.attempt_id})
    op = op.model_copy(update={"operation_id": "independent-attempt-review"})
    control = controls.bind(op)
    snapshot = read_fact(
        store,
        EvidenceRef.model_validate(data["trace_snapshot_ref"]),
        TraceSnapshot,
        control,
    )
    trace = read_fact(
        store, EvidenceRef.model_validate(data["trace_ref"]), InteractionTrace, control
    )
    assert trace == snapshot.project().sealed
    executions = tuple(
        read_fact(store, EvidenceRef.model_validate(ref), LocalActorExecution, control)
        for ref in data["executions"]
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
    actor_resource = review_resource(
        actor["resource_record"], request.model_allocation, store, control
    )
    browser_resource = review_resource(
        site["prepared_browser"]["browser_record"],
        request.browser_allocation,
        store,
        control,
    )
    site_record = ResourceRecord.model_validate_json(json.dumps(site["record"]))
    assert site_record.token.owner == request.scope.owner
    review_resource(site["record"], site_record.token, store, control)
    for execution in executions:
        assert (
            execution.call.binding.acquired_ref
            == ResourceRecord.model_validate_json(json.dumps(actor["resource_record"]))
            .events[2]
            .evidence[0]
        )
        assert (
            execution.guard.model_dump(mode="json")
            == actor_resource["acquired"]["owner_guard"]
        )
    initial, reset = review_state(site, store, control)
    assert initial.prepared.scope == trace.scope and initial.public_task == request.task
    assert initial.observation_ref == trace.initial_observation_ref
    assert reset.plan.attempt_allocations == (request.browser_allocation,)
    judgment = data["judgment"]
    from lab_generate_skill.sites.gitlab.evidence_schema import (
        SshKeyEvidence,
        GroupEvidence,
    )
    from lab_generate_skill.bootstrap.gitlab_group_evaluation import (
        gitlab_group_evaluator,
    )
    from gitlab_source_selection import group_task
    from lab_generate_skill.bootstrap.gitlab_ssh_evaluation import gitlab_ssh_evaluator

    from lab_generate_skill.sites.reddit.evidence_schema import ImageEvidence
    from lab_generate_skill.bootstrap.reddit_image_evaluation import (
        reddit_image_evaluator,
    )

    selected: (
        OrderEtaEvidence
        | ProductDescriptionEvidence
        | SshKeyEvidence
        | GroupEvidence
        | ImageEvidence
    )
    contract = read_fact(
        store,
        EvidenceRef.model_validate(judgment["contract_ref"]),
        EvaluationContract,
        control,
    )
    assert (
        contract.identity == request.task.identity
        and contract.attempt_id == request.scope.attempt_id
    )
    selection_ref = EvidenceRef.model_validate(judgment["selection_ref"])
    if reddit:
        selected = read_fact(store, selection_ref, ImageEvidence, control)
        assert selected.trace_snapshot_ref == EvidenceRef.model_validate(
            data["trace_snapshot_ref"]
        )
    elif gitlab:
        if group_task(contract.identity):
            selected = read_fact(store, selection_ref, GroupEvidence, control)
        else:
            selected = read_fact(store, selection_ref, SshKeyEvidence, control)
    elif shopping:
        selected = read_fact(store, selection_ref, OrderEtaEvidence, control)
    else:
        selected = read_fact(store, selection_ref, ProductDescriptionEvidence, control)
    saved = read_fact(
        store,
        EvidenceRef.model_validate(judgment["evaluation_ref"]),
        Evaluation,
        control,
    )
    assert selected.trace_ref == EvidenceRef.model_validate(data["trace_ref"])
    assert (
        contract.public_task_ref == initial.binding.public_task_ref
        and contract.completion_spec_ref == initial.binding.private_spec_ref
    )
    from lab_generate_skill.ports.evaluator import Evaluator

    evaluator: Evaluator
    if isinstance(selected, ImageEvidence):
        evaluator = reddit_image_evaluator(selected)
    elif isinstance(selected, GroupEvidence):
        evaluator = gitlab_group_evaluator(selected)
    elif isinstance(selected, SshKeyEvidence):
        evaluator = gitlab_ssh_evaluator(selected)
    elif isinstance(selected, OrderEtaEvidence):
        evaluator = OrderEtaEvaluator(selected)
    else:
        evaluator = ProductDescriptionEvaluator(selected)
    assert saved == evaluator.evaluate(contract, store, control)
    native_review = None
    if isinstance(selected, ImageEvidence):
        from reddit_actor_review import review_reddit_judgment, review_reddit_reset

        native_review = review_reddit_judgment(
            contract, selected, saved, store, control
        )
        review_reddit_reset(site, reset, store, control)
    elif isinstance(selected, (SshKeyEvidence, GroupEvidence)):
        from gitlab_actor_review import review_gitlab_judgment, review_gitlab_reset

        native_review = review_gitlab_judgment(
            contract, selected, saved, store, control
        )
        review_gitlab_reset(site, reset, store, control)
    else:
        assert saved.status in ("success", "failure")
    assert (
        not actor.get("paid_calls")
        and not data.get("errors")
        and actor["local_staging_removed_after_step_closure"]
    )
    assert site["private_root_removed"] and not Path(site["private_root"]).exists()
    assert (
        actor_path.read_bytes() == original_actor
        and site_path.read_bytes() == original_site
    )
    verify_source(Path(actor["software_receipt"]), source_root=execution_source)
    report = dict(
        engineering_only=True,
        formal_source_admission=False,
        independent_process=os.getpid(),
        original_job_root=str(root),
        original_execution_source=str(execution_source),
        reviewer_source=str(Path(__file__).resolve().parents[2]),
        actor_facts_sha256=hashlib.sha256(original_actor).hexdigest(),
        site_facts_sha256=hashlib.sha256(original_site).hexdigest(),
        actor=summary,
        evaluation=saved.model_dump(mode="json"),
        baseline="ready",
        reset="safe",
        resources="original_actor_browser_site_closed",
        read_only=True,
        browser_configuration_sha256=hashlib.sha256(
            json.dumps(browser_resource["configuration"], sort_keys=True).encode()
        ).hexdigest(),
    )
    if gitlab or reddit:
        report["native_review"] = native_review
        report["business_accepted"] = saved.status in ("success", "failure")
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / (label + "-actor-independent-review.json")
    ).write_text(json.dumps(report, indent=2) + "\n")
