"""Consume an explicit original pre-registration failure, never replay it.

The old attempt, diagnostics and missing Reset remain unchanged. This reader
supports only the closed acquiring-only branch with a persisted unstarted
browser and a traceback at the selected installed site's pre-registration gate.
"""

import ast
import json
from pathlib import PurePosixPath
from lab_generate_skill.domain.closed_stage_acquisition import (
    ClosedPreRegistrationStageEvidence,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_execution_result import TaskFailureContext
from lab_generate_skill.domain.task_failure_evidence import TaskModuleFailureEvidence
from lab_generate_skill.domain.task_finalization import UnstartedTaskBrowser
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_reads import StateReads


def _one(refs: tuple[EvidenceRef, ...], schema: str) -> EvidenceRef:
    matches = [r for r in refs if r.content_schema == schema]
    if len(matches) != 1:
        raise OwnershipConflict(
            "Original acquisition review requires one exact " + schema
        )
    return matches[0]


def verify_pre_registration_failure(
    reads: StateReads,
    inputs: ClosedPreRegistrationStageEvidence,
    source: ExecutionTaskSource,
    snapshot: RunSnapshot,
    control: OperationControl,
) -> None:
    control.checkpoint()
    _, attempts = snapshot.project()
    if len(attempts) != 1:
        raise OwnershipConflict("Pre-registration review requires one original attempt")
    attempt = attempts[0]
    if (
        attempt.binding != source.intent.binding
        or attempt.stop_reason != "error"
        or tuple(e.stage for e in attempt.events)
        != ("planned", "acquiring", "closing", "restoring", "sealed")
        or attempt.primary_error is None
        or len(attempt.cleanup_errors) != 1
    ):
        raise OwnershipConflict(
            "Prior attempt progressed beyond the selected failed acquisition"
        )
    plan_ref = _one(attempt.events[0].outputs, "task-execution-plan/2")
    plan = reads.parse(plan_ref, "task-execution-plan/2", TaskExecutionPlan, control)
    if plan.intent != source.intent or plan.source_ref != inputs.source_ref:
        raise OwnershipConflict("Prior acquisition plan changed the original source")
    failure_ref = _one(attempt.primary_error.evidence, "task-failure-context/2")
    failure = reads.parse(
        failure_ref, "task-failure-context/2", TaskFailureContext, control
    )
    module_ref = _one(failure.references, "task-module-failure-evidence/1")
    module = reads.parse(
        module_ref, "task-module-failure-evidence/1", TaskModuleFailureEvidence, control
    )
    if (
        failure.intent != source.intent
        or failure.failure_type != "TaskPreparationUnconfirmed"
        or plan_ref not in failure.references
        or module.intent != source.intent
        or module.failure_type != failure.failure_type
        or module.confirmed_references
        or module.candidate_references
        or module.malformed_attributes
    ):
        raise OwnershipConflict(
            "Prior preparation has produced or unresolved task effects"
        )
    cleanup_ref = _one(attempt.cleanup_errors[0].evidence, "task-failure-context/2")
    cleanup = reads.parse(
        cleanup_ref, "task-failure-context/2", TaskFailureContext, control
    )
    if (
        cleanup.intent != source.intent
        or cleanup.failure_type != "TaskFinalizationUnconfirmed"
        or failure_ref not in cleanup.references
    ):
        raise OwnershipConflict("Original missing-prepare cleanup diagnostics changed")
    closed_ref = _one(attempt.events[3].outputs, "closed-task-resources/1")
    closed = reads.parse(
        closed_ref, "closed-task-resources/1", ClosedTaskResources, control
    )
    if (
        closed_ref not in cleanup.references
        or closed.reset_plan_ref != plan.reset_plan_ref
        or len(closed.closures) != 1
        or closed.reset_plan.scope.owner != source.run.owner
        or closed.reset_plan.scope.task != source.task.identity
        or closed.reset_plan.scope.attempt_id != source.intent.binding.attempt_id
    ):
        raise OwnershipConflict("Original unstarted closure changed task/reset scope")
    closure = reads.parse(
        closed.closure_refs[0], "closure-receipt/1", ClosureReceipt, control
    )
    unstarted_ref = _one(closure.evidence, "unstarted-task-browser/2")
    unstarted = reads.parse(
        unstarted_ref, "unstarted-task-browser/2", UnstartedTaskBrowser, control
    )
    if (
        closure != closed.closures[0]
        or closure.primary_error is not None
        or closure.cleanup_errors
        or unstarted.token != closure.token
        or unstarted.scope != closed.reset_plan.scope
        or unstarted.reset_plan_ref != plan.reset_plan_ref
        or unstarted.operation.operation_id != closure.operation_id
        or unstarted.owner_phase != "not_constructed"
        or unstarted.registration != "absent"
    ):
        raise OwnershipConflict(
            "Original browser was started or closure is unconfirmed"
        )
    preparation = json.loads(reads.read(unstarted.preparation_declaration_ref, control))
    finalization = json.loads(
        reads.read(unstarted.finalization_declaration_ref, control)
    )
    if (
        preparation.get("scope") != unstarted.scope.model_dump(mode="json")
        or finalization.get("scope") != unstarted.scope.model_dump(mode="json")
        or preparation.get("site_spec_ref")
        != inputs.site_spec_ref.model_dump(mode="json")
    ):
        raise OwnershipConflict("Original unstarted declarations changed selected site")
    site = reads.parse(
        inputs.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
    )
    if (
        site.token.owner != source.run.owner
        or site.configuration.installation.manifest_ref != source.run.release_ref
    ):
        raise OwnershipConflict("Original site declaration changed its owner/release")
    artifacts = [
        a
        for a in site.configuration.installation.manifest.artifacts
        if a.artifact_id == "installed-code"
    ]
    if len(artifacts) != 1:
        raise OwnershipConflict("One selected installed site adapter is required")
    code = artifacts[0]
    relative = "lab_generate_skill/adapters/sites/resource.py"
    files = [f for f in code.files if f.path == relative]
    if len(files) != 1 or (files[0].sha256, files[0].size_bytes) != (
        inputs.site_adapter_ref.sha256,
        inputs.site_adapter_ref.size_bytes,
    ):
        raise OwnershipConflict(
            "Retained site adapter differs from the original installation"
        )
    adapter = reads.read(inputs.site_adapter_ref, control).decode("utf-8")
    functions = [
        n
        for n in ast.parse(adapter).body
        if isinstance(n, ast.FunctionDef) and n.name == "registered_site"
    ]
    if len(functions) != 1:
        raise OwnershipConflict("One original registered-site function required")
    calls = {}
    for name in ("authority.authorize_spawn", "journal.register", "channel.start"):
        matches = [
            n
            for n in ast.walk(functions[0])
            if isinstance(n, ast.Call) and ast.unparse(n.func) == name
        ]
        if len(matches) != 1:
            raise OwnershipConflict(
                "Unsupported original site registration control flow"
            )
        calls[name] = matches[0]
    gate = calls["authority.authorize_spawn"]
    if (
        not gate.lineno
        < calls["journal.register"].lineno
        < calls["channel.start"].lineno
    ):
        raise OwnershipConflict(
            "Original site startup preceded its durable registration"
        )
    # Require the gate as a straight-line top-level statement before registration.
    if not any(isinstance(n, ast.Expr) and n.value is gate for n in functions[0].body):
        raise OwnershipConflict(
            "Original pre-registration gate was conditional or indirect"
        )
    trace = reads.read(inputs.traceback_ref, control).decode("utf-8")
    marker = f'File "{PurePosixPath(code.root) / relative}", line {gate.lineno}, in registered_site'
    if (
        trace.count(marker) != 1
        or "authority.authorize_spawn(spec, operation, control)" not in trace
    ):
        raise OwnershipConflict(
            "Original failure does not locate the pre-registration gate"
        )
    member = json.loads(reads.read(inputs.member_ref, control))
    if (
        member.get("source_task_id") != source.task.identity.source_task_id
        or member.get("job_time_limit", {}).get("execution", {}).get("job_id")
        != source.run.owner.job_id
        or member.get("metadata_admission_revoked") is not True
        or member.get("source_owner_sealed") is not True
        or member.get("paid_calls") != 0
        or member.get("actual_actor_members_executed") != []
        or member.get("business_result") != "not_executed"
        or "execution_site_record" not in member
        or member["execution_site_record"] is not None
        or "execution_browser_record" not in member
        or member["execution_browser_record"] is not None
        or member.get("site_resource_physical_observations") != []
    ):
        raise OwnershipConflict(
            "Original owner result contains actions, native resources or unclosed metadata"
        )
    control.checkpoint()
