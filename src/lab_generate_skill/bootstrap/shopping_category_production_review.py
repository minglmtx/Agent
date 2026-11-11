"""Independent Shopping category read-only review using original Actor and business algorithms.

Reuses the existing original Actor input/count review and native evaluation /
Reset algorithms. Site/browser access uses the production strict closed-domain
reader. The only storage capability in this child rejects every write.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.bootstrap.shopping_category_closed_preparation import (
    closed_category_preparations,
)
from lab_generate_skill.bootstrap.shopping_category_closed_source import (
    closed_category_source_contexts,
)
from lab_generate_skill.bootstrap.shopping_category_evaluation import (
    shopping_category_evaluator,
)
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from lab_generate_skill.adapters.plans.closed_resource import (
    review_resource as review_site_resource,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceReceipt,
    EquivalenceChecks,
    EquivalenceInputs,
    assemble_equivalence,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    assemble_public_context,
)
from lab_generate_skill.domain.task_execution import TaskCaptureResult
from lab_generate_skill.sites.shopping.tasks.navigation_equivalence import (
    CategoryNavigationInitialComparison,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state_checks import (
    CategoryNavigationStateChecks,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    assemble_baseline,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evaluation import Evaluation, EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    ResourceRecord,
    OperationContext,
    CancellationRef,
)
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt, assemble_reset
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.state_qualification import ResetSelection
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.runtime.lifecycle import OperationGuards
from .source_execution_projection import original_source_projection
from .closed_actor_review import review_actor
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from .closed_actor_resource_review import review_actor_resource


class NoReviewCancellationSelection:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise ValueError(
            "Bounded read-only review cannot select a live control channel"
        )


def review(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    facts = json.loads(raw)
    if (
        not isinstance(facts, dict)
        or facts.get("schema_version")
        != "shopping-category-owned-closed-review-inputs/1"
        or type(facts.get("original_process")) is not int
        or facts["original_process"] <= 0
        or facts["original_process"] == os.getpid()
        or facts["engineering_only"] is not True
    ):
        raise ValueError("Separate original engineering review process required")
    site = SiteResourceSpec.model_validate_json(json.dumps(facts["site"]))
    browser = BrowserResourceSpec.model_validate_json(json.dumps(facts["browser"]))
    site_record = ResourceRecord.model_validate_json(json.dumps(facts["site_record"]))
    browser_record = ResourceRecord.model_validate_json(
        json.dumps(facts["browser_record"])
    )
    started = SiteResourceStarted.model_validate_json(json.dumps(facts["started"]))
    actor_record = ResourceRecord.model_validate_json(json.dumps(facts["actor_record"]))
    contract = EvaluationContract.model_validate_json(
        json.dumps(facts["evaluation_contract"])
    )
    source_material = ClosedCategoryNavigationReadMaterial.model_validate_json(
        json.dumps(facts["source_material"])
    )
    inputs = site.configuration.shopping_category_inputs
    scope = browser.configuration.spec.scope
    if (
        site.configuration.site_id != "shopping"
        or inputs is None
        or inputs.scope != scope
        or scope.task.site != "shopping"
        or scope.task.split != "train"
        or contract.scope != "engineering"
        or (contract.identity, contract.attempt_id) != (scope.task, scope.attempt_id)
        or any(
            record.state != "closed"
            for record in (site_record, browser_record, actor_record)
        )
        or any(
            record.token.owner != scope.owner
            for record in (site_record, browser_record, actor_record)
        )
        or site_record.token != site.token
        or browser_record.token != browser.token
        or source_material.site.token.owner != scope.owner
        or source_material.site.token == site.token
        or source_material.browser.token == browser.token
        or source_material.site.configuration.files.node_root
        == site.configuration.files.node_root
    ):
        raise ValueError(
            "Closed independent same-owner Shopping category instances and exact evaluation required"
        )
    op = OperationContext(
        operation_id="independent-shopping18-review",
        run_id=site.token.owner.run_id,
        owner_id=site.token.owner.owner_id,
        attempt_id=browser.token.attempt_id,
        mode="cleanup",
        parent_operation_id="execution.task",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
    )
    controls = OperationGuards(SystemClock(), NoReviewCancellationSelection())
    control = controls.bind(op)
    store = ReadOnlyEvidence(
        Path(facts["evidence_root"]),
        max_object_bytes=64 * 1024**2,
        reuse_within_proof=True,
    )
    reads = StateReads(store)
    for spec, record in ((site, site_record), (browser, browser_record)):
        reviewed = review_site_resource(
            record.model_dump(mode="json"), spec.token, store, control
        )
        if reviewed["configuration"] != spec.model_dump(mode="json"):
            raise ValueError(
                "Independent Shopping category resource configuration changed"
            )
    initial = BaselineInputs.model_validate_json(json.dumps(facts["baseline_inputs"]))
    baseline = reads.parse(
        EvidenceRef.model_validate_json(json.dumps(facts["baseline_ref"])),
        "baseline-receipt/1",
        BaselineReceipt,
        control,
    )
    reset_inputs = ResetInputs.model_validate_json(json.dumps(facts["reset_inputs"]))
    reset = reads.parse(
        EvidenceRef.model_validate_json(json.dumps(facts["reset_ref"])),
        "reset-receipt/1",
        ResetReceipt,
        control,
    )
    if (
        assemble_baseline(initial, baseline.operation) != baseline
        or baseline.status != "ready"
        or assemble_reset(reset_inputs, reset.operation) != reset
        or reset.status != "safe"
    ):
        raise ValueError("Independent original Baseline/Reset recomputation differs")
    preparations = closed_category_preparations(initial, site, browser, store, controls)
    envelope = reads.parse(
        EvidenceRef.model_validate_json(json.dumps(facts["attempt_ref"])),
        "execution-attempt-result/1",
        TaskAttemptResult,
        control,
    )
    receipt = reads.parse(
        envelope.execution_ref, "executed-task-receipt/2", ExecutedTaskReceipt, control
    )
    request = reads.parse(
        receipt.actor_request_ref, "actor-run-request/2", ActorRunRequest, control
    )
    baseline_ref = EvidenceRef.model_validate_json(json.dumps(facts["baseline_ref"]))
    reset_ref = EvidenceRef.model_validate_json(json.dumps(facts["reset_ref"]))
    if (
        receipt.intent != envelope.intent
        or receipt.baseline_ref != baseline_ref
        or receipt.reset_ref != reset_ref
        or (receipt.generations, receipt.interactions)
        != (envelope.generations, envelope.interactions)
    ):
        raise ValueError(
            "Independent completed receipt changed original facts/counters"
        )
    equivalence = reads.parse(
        receipt.equivalence_ref, "equivalence-receipt/1", EquivalenceReceipt, control
    )
    original_context = closed_category_source_contexts(
        source_material, store, controls, op
    ).load_context(source_material.context_ref, op)
    source_baseline = reads.parse(
        original_context.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    source_reset = reads.parse(
        original_context.reset_ref, "reset-receipt/1", ResetReceipt, control
    )
    public = reads.parse(
        original_context.public_context_ref,
        "public-construction-context/1",
        PublicConstructionContext,
        control,
        visibility="public",
    )
    source_inputs = PublicContextInputs(
        context=public,
        context_ref=original_context.public_context_ref,
        baseline_inputs=BaselineEvidenceReader(store).verify(source_baseline, control),
        baseline=source_baseline,
        baseline_ref=original_context.baseline_ref,
        reset_inputs=ResetEvidenceReader(store).verify(source_reset, control),
        reset=source_reset,
        reset_ref=original_context.reset_ref,
    )
    if (
        assemble_public_context(source_inputs, original_context.operation)
        != original_context
    ):
        raise ValueError("Independent original source context differs")
    comparison = reads.parse(
        equivalence.checks_ref, "equivalence-checks/1", EquivalenceChecks, control
    )
    measured = CategoryNavigationInitialComparison(store).compare(
        source_inputs, initial, control
    )
    comparison_inputs = EquivalenceInputs(
        source_inputs=source_inputs,
        source=original_context,
        source_ref=source_material.context_ref,
        candidate_inputs=initial,
        candidate=baseline,
        candidate_ref=baseline_ref,
        checks=comparison,
        checks_ref=equivalence.checks_ref,
    )
    if (
        comparison.checks != measured
        or measured.status != "pass"
        or assemble_equivalence(comparison_inputs, equivalence.operation) != equivalence
        or equivalence.status != "equivalent"
    ):
        raise ValueError(
            "Independent original source/candidate initial equivalence differs"
        )
    trace = reads.parse(
        receipt.trace_ref, "interaction-trace/1", InteractionTrace, control
    )
    snapshot = TraceSnapshot.model_validate_json(json.dumps(facts["trace_snapshot"]))
    executions = tuple(
        LocalActorExecution.model_validate_json(json.dumps(v))
        for v in facts["model_executions"]
    )
    if snapshot.project().sealed != trace or (
        request.scope,
        request.task,
        request.initial_observation_ref,
    ) != (initial.prepared.scope, initial.public_task, initial.observation_ref):
        raise ValueError("Original Actor trace/initial source differs")
    original_projection = original_source_projection(
        request, snapshot.plan, store, control
    )
    summary = review_actor(
        request,
        snapshot,
        executions,
        store,
        controls,
        op,
        project=(
            build_actor_projection(original_projection)
            if request.schema_version == "actor-run-request/1"
            else None
        ),
        context=closed_actor_context(
            request,
            executions,
            store,
            EvidenceObservations(store, controls),
            control=control,
        ),
    )
    actor_record = ResourceRecord.model_validate_json(json.dumps(facts["actor_record"]))
    actor = review_actor_resource(
        facts["actor_record"], request.model_allocation, store, control
    )
    if (
        request.browser_allocation != browser.token
        or reset_inputs.plan.attempt_allocations != (browser.token,)
    ):
        raise ValueError("Review changed the original Actor/browser allocations")
    for execution in executions:
        if (
            execution.call.binding.acquired_ref != actor_record.events[2].evidence[0]
            or execution.guard.model_dump(mode="json")
            != actor["acquired"]["owner_guard"]
        ):
            raise ValueError("Model exchange changed original acquired Actor")
    selected_ref = EvidenceRef.model_validate_json(
        json.dumps(facts["selected_evidence_ref"])
    )
    captured = reads.parse(
        receipt.capture_ref, "task-capture-result/1", TaskCaptureResult, control
    )
    if captured.contract != contract or selected_ref not in captured.references:
        raise ValueError(
            "Independent capture selection differs from original task result"
        )
    saved = reads.parse(receipt.evaluation_ref, "evaluation/1", Evaluation, control)
    selected = reads.parse(
        selected_ref,
        "shopping-category-navigation-evidence/1",
        CategoryNavigationEvidence,
        control,
    )
    evaluator = shopping_category_evaluator(selected, preparations, site, started, op)
    if evaluator.evaluate(contract, store, control) != saved:
        raise ValueError("Independent original Shopping category judgment differs")
    reset_ref = EvidenceRef.model_validate_json(
        json.dumps(facts["reset_selection_ref"])
    )
    selected_reset = reads.parse(
        reset_ref, "reset-selection/1", ResetSelection, control
    )
    checks = CategoryNavigationStateChecks(store).reset(
        selected_reset, reset_ref, control
    )
    if (
        checks.task,
        checks.environment,
        checks.health,
        checks.plan,
        checks.closures,
    ) != (
        reset_inputs.task.checks,
        reset_inputs.environment.checks,
        reset_inputs.health.checks,
        reset_inputs.plan,
        reset_inputs.closures,
    ):
        raise ValueError("Independent complete native Reset file checks differ")
    if (summary["generations"], summary["interactions"]) != (
        receipt.generations,
        receipt.interactions,
    ):
        raise ValueError("Independent original Actor/receipt counts differ")
    if path.read_bytes() != raw:
        raise ValueError("Original review input changed during independent reading")
    return {
        "passed": True,
        "separate_process": True,
        "read_only": True,
        "business_result": saved.status,
        "reset": "safe",
        "generations": summary["generations"],
        "interactions": summary["interactions"],
        "formal_training_qualification": False,
    }


if __name__ == "__main__":
    print(json.dumps(review(Path(sys.argv[1])), sort_keys=True))
