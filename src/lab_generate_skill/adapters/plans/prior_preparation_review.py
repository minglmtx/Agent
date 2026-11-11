"""Review an ended, isolated preparation failure without repairing old history.

No request is retried or unknown settled. This reader is only one input to
explicit stage selection; the current canonical claim and caller gates remain
responsible for authorization.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from lab_generate_skill.adapters.slurm.accounting import (
    AccountingFact,
    parse_accounting,
)
from lab_generate_skill.domain.claims import SourceClaimRecord, SourceClaimReceipt
from lab_generate_skill.domain.ended_stage_preparation import (
    EndedPreparationStageEvidence,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.lifecycle import ClosureReceipt, ResourceRecord
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.run_plan import ExecutionWorkload, RunPlan
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_execution_result import TaskFailureContext
from lab_generate_skill.domain.task_failure_evidence import TaskModuleFailureEvidence
from lab_generate_skill.domain.task_finalization import UnstartedTaskBrowser
from lab_generate_skill.ports.lifecycle import OperationControl
from .stage_parent import RetainedStageParentChecks
from .prior_preparation_resources import verify_preparation_resources


@dataclass(frozen=True)
class EndedPreparationFacts:
    inputs: EndedPreparationStageEvidence
    claim: SourceClaimRecord
    source: ExecutionTaskSource
    run: RunSnapshot
    plan: RunPlan
    resource: ResourceRecord
    site: ResourceRecord
    session: EvidenceSessionSnapshot
    accounting: AccountingFact


def _one(refs: tuple[EvidenceRef, ...], schema: str) -> EvidenceRef:
    selected = [r for r in refs if r.content_schema == schema]
    if len(selected) != 1:
        raise OwnershipConflict("Preparation review requires one exact " + schema)
    return selected[0]


def load_ended_preparation(
    parent: RetainedStageParentChecks,
    reference: EvidenceRef,
    control: OperationControl,
) -> EndedPreparationFacts:
    reads = parent.reads
    inputs = reads.parse(
        reference,
        "ended-preparation-stage-evidence/1",
        EndedPreparationStageEvidence,
        control,
    )
    claim = reads.parse(inputs.claim_ref, "source-claim/1", SourceClaimRecord, control)
    SourceClaimReceipt(record=claim, reference=inputs.claim_ref)
    source = reads.parse(
        inputs.source_ref, "execution-task-source/2", ExecutionTaskSource, control
    )
    snapshot = reads.parse(
        inputs.run_ref, "run-journal-snapshot/2", RunSnapshot, control
    )
    run, attempts = snapshot.project()
    plan = reads.parse(source.run.plan_ref, "run-plan/3", RunPlan, control)
    plan.check_binding(source.run)
    if (
        source.frozen_origin is None
        or claim.binding.run != source.run
        or claim.binding.task != source.task
        or source.intent.binding.claim_ref != inputs.claim_ref
        or snapshot.binding != source.run
        or len(attempts) != 1
        or run.stage not in ("running", "sealed")
        or (run.stage == "sealed" and run.stop_reason != "error")
        or plan.purpose != "engineering"
        or plan.split != "train"
        or plan.tasks != (source.task,)
        or not isinstance(plan.workload, ExecutionWorkload)
        or len(plan.models) != 1
        or plan.models[0].role != "actor"
        or plan.models[0].provider != "fixed-actor-worker"
        or plan.models[0].paid
        or plan.budget is not None
        or plan.resources.max_parallel_tasks != 1
    ):
        raise OwnershipConflict("Original failed engineering stage identity changed")
    attempt = attempts[0]
    if (
        attempt.binding != source.intent.binding
        or attempt.stop_reason != "timeout"
        or tuple(e.stage for e in attempt.events)
        not in (
            ("planned", "acquiring", "closing", "restoring", "sealed"),
            ("planned", "acquiring", "preparing", "closing", "restoring", "sealed"),
        )
        or attempt.primary_error is None
        or len(attempt.cleanup_errors) != 1
    ):
        raise OwnershipConflict("Original task progressed beyond failed preparation")
    task_plan_ref = _one(attempt.events[0].outputs, "task-execution-plan/2")
    task_plan = reads.parse(
        task_plan_ref, "task-execution-plan/2", TaskExecutionPlan, control
    )
    failure_ref = _one(attempt.primary_error.evidence, "task-failure-context/2")
    failure = reads.parse(
        failure_ref, "task-failure-context/2", TaskFailureContext, control
    )
    module = reads.parse(
        _one(failure.references, "task-module-failure-evidence/1"),
        "task-module-failure-evidence/1",
        TaskModuleFailureEvidence,
        control,
    )
    if (
        task_plan.intent != source.intent
        or task_plan.source_ref != inputs.source_ref
        or failure.intent != source.intent
        or failure.failure_type != "TaskPreparationUnconfirmed"
        or task_plan_ref not in failure.references
        or module.intent != source.intent
        or module.failure_type != failure.failure_type
        or len(module.confirmed_references) != 2
        or module.candidate_references
        or module.malformed_attributes
    ):
        raise OwnershipConflict("Original preparation contains unconfirmed effects")
    started_ref = _one(module.confirmed_references, "site-resource-started/1")
    started = reads.parse(
        started_ref, "site-resource-started/1", SiteResourceStarted, control
    )
    acquired = reads.parse(
        _one(module.confirmed_references, "site-task-acquired/1"),
        "site-task-acquired/1",
        SiteTaskAcquired,
        control,
    )
    actor = reads.parse(
        inputs.actor_resource_ref, "resource-record/2", ResourceRecord, control
    )
    site = reads.parse(
        inputs.site_resource_ref, "resource-record/2", ResourceRecord, control
    )
    if (
        acquired.scope.owner != source.run.owner
        or acquired.scope.task != source.task.identity
        or acquired.scope.attempt_id != source.intent.binding.attempt_id
        or acquired.site_started_ref != started_ref
        or len(site.events) < 3
        or site.events[1].evidence != (acquired.resource_intent_ref,)
        or site.events[2].evidence != (acquired.resource_acquired_ref,)
        or started.ready.controller.target.execution.job_id != source.run.owner.job_id
    ):
        raise OwnershipConflict("Original task acquisition changed its site scope")
    site_fact = json.loads(reads.read(acquired.resource_acquired_ref, control))
    declaration = reads.parse(
        acquired.declaration_ref,
        "site-task-preparation-plan/2",
        SiteTaskPreparationPlan,
        control,
    )
    acquisition = reads.parse(
        acquired.resource_intent_ref,
        "resource-acquisition-intent/1",
        ResourceAcquisitionIntent,
        control,
    )
    if (
        started.ready.model_dump(mode="json") != site_fact["details"]["ready"]
        or declaration.scope != acquired.scope
        or declaration.site_spec_ref != acquisition.configuration_ref
    ):
        raise OwnershipConflict("Original preparation declaration/ready target changed")
    closed_ref = _one(attempt.events[-2].outputs, "closed-task-resources/1")
    closed = reads.parse(
        closed_ref, "closed-task-resources/1", ClosedTaskResources, control
    )
    cleanup = reads.parse(
        _one(attempt.cleanup_errors[0].evidence, "task-failure-context/2"),
        "task-failure-context/2",
        TaskFailureContext,
        control,
    )
    if (
        cleanup.intent != source.intent
        or cleanup.failure_type != "TaskFinalizationUnconfirmed"
        or failure_ref not in cleanup.references
        or closed_ref not in cleanup.references
        or closed.reset_plan_ref != task_plan.reset_plan_ref
        or len(closed.closures) != 1
        or closed.reset_plan.scope != acquired.scope
    ):
        raise OwnershipConflict(
            "Original unconfirmed Reset/cleanup attribution changed"
        )
    closure = reads.parse(
        closed.closure_refs[0], "closure-receipt/1", ClosureReceipt, control
    )
    unstarted = reads.parse(
        _one(closure.evidence, "unstarted-task-browser/2"),
        "unstarted-task-browser/2",
        UnstartedTaskBrowser,
        control,
    )
    if (
        closure != closed.closures[0]
        or closure.primary_error is not None
        or closure.cleanup_errors
        or unstarted.token != closure.token
        or unstarted.scope != acquired.scope
        or unstarted.reset_plan_ref != task_plan.reset_plan_ref
        or unstarted.preparation_declaration_ref != acquired.declaration_ref
        or unstarted.operation.operation_id != closure.operation_id
        or unstarted.owner_phase != "not_constructed"
        or unstarted.registration != "absent"
    ):
        raise OwnershipConflict(
            "Original browser construction or effects are unresolved"
        )
    session = reads.parse(
        inputs.session_ref,
        "evidence-session-snapshot/3",
        EvidenceSessionSnapshot,
        control,
    )
    if (
        session.binding.owner != source.run.owner
        or session.binding.scope != "run"
        or not session.entries
    ):
        raise OwnershipConflict("Original metadata history is missing or changed")
    request_refs = set()
    for entry in session.entries:
        control.checkpoint()
        if entry.reusable and (
            entry.outcome is None or entry.outcome.status != "succeeded"
        ):
            raise OwnershipConflict(
                "Original metadata contains an unsuccessful operation"
            )
        ref = entry.intent.reference
        if ref.content_schema == "site-task-request/2" and ref not in request_refs:
            request_refs.add(ref)
            request = reads.parse(ref, "site-task-request/2", SiteTaskRequest, control)
            if request.operation.run_id == source.run.owner.run_id:
                raise OwnershipConflict(
                    "Original native task request cannot be replayed"
                )
    execution = verify_preparation_resources(
        parent, inputs, source, actor, site, session, control
    )
    accounting = parse_accounting(reads.read(inputs.accounting_ref, control), execution)
    if (
        accounting.state != "FAILED"
        or accounting.ended_at_epoch is None
        or accounting.exit_status == 0
        or accounting.exit_signal != 0
    ):
        raise OwnershipConflict("Original failed execution is not explicitly terminal")
    if inputs.process_observation_ref is not None:
        proof = json.loads(reads.read(inputs.process_observation_ref, control))
        if (
            datetime.fromisoformat(proof["observed_at"]).timestamp()
            < accounting.ended_at_epoch
        ):
            raise OwnershipConflict(
                "Original process observation predates execution ending"
            )
    member = json.loads(reads.read(inputs.member_ref, control))
    if (
        member.get("source_task_id") != source.task.identity.source_task_id
        or member.get("job_time_limit", {}).get("execution")
        != execution.model_dump(mode="json")
        or member.get("source_owner_sealed") is not True
        or member.get("metadata_admission_revoked") is not True
        or member.get("paid_calls") != 0
        or member.get("actual_actor_members_executed") != []
        or member.get("business_result") != "not_executed"
        # The typed original UnstartedTaskBrowser proof above is mandatory.
        # Optional summary fields cannot replace it or contradict it.
        or member.get("execution_browser_record") is not None
        or (run.stage == "running" and inputs.process_observation_ref is None)
    ):
        raise OwnershipConflict(
            "Original member has active admission or task/model work"
        )
    control.checkpoint()
    return EndedPreparationFacts(
        inputs, claim, source, snapshot, plan, actor, site, session, accounting
    )
