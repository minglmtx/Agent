"""Real CAS/claim/source consumers with explicitly unit-only admission.

The original fixture is not a safely closed production parent. Its unit
authority proves software flow only; no caller/native/business grant follows.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
from lab_generate_skill.bootstrap.execution_task_source import (
    publish_execution_task_source,
)
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskInputs,
    ExecutionTaskSource,
)
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.run_plan import ExecutionWorkload, RunPlan
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from construction_storage_fixtures import put
from claim_fixtures import operation
from execution_task_fixtures import ExecutionCase, execution_case
from stage_validation_fixtures import UnitStageAuthority


class UnitHistoricalContext(ClosedSourceContexts):
    def __init__(self, case: ExecutionCase) -> None:
        super().__init__(
            case.source.data.adapter, case.source.source.source_context_receipt_ref
        )
        self.case, self.denied, self.calls = case, False, 0

    def load_context(
        self, reference: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt:
        self.calls += 1
        if self.denied:
            raise PermissionError("unit frozen context revoked")
        historical = read_operation(self.case.source.inputs.source.operation, op)
        return super().load_context(reference, historical)


@dataclass
class FrozenSourceCase:
    parent: ExecutionCase
    binding: SourceClaimBinding
    origin: FrozenExecutionOrigin
    authority: UnitStageAuthority
    claims: FileSourceStageValidations
    contexts: UnitHistoricalContext
    reader: OriginalExecutionTaskSource
    source: ExecutionTaskSource
    source_ref: EvidenceRef
    plan: TaskExecutionPlan


def frozen_source_case(root: Path) -> FrozenSourceCase:
    parent = execution_case(root / "parent")
    original = parent.source
    store, controls = original.data.store, original.data.adapter.controls
    source = original.source
    record = original.claims.require_source(
        source.intent.binding.claim_ref,
        source.run,
        source.task,
        original.data.inputs.source.operation.model_copy(update={"attempt_id": None}),
    )
    receipt = SourceClaimReceipt(
        record=record, reference=source.intent.binding.claim_ref
    )
    release = put(store, {"unit_changed_release": True}, "release-manifest/1")
    authorization = put(
        store,
        {"unit_only_authorization": True},
        "task-stage-validation-authorization/1",
    )
    inputs = ExecutionTaskInputs(
        task_binding_ref=parent.plan.evaluation.task_contract_ref,
        source_context_receipt_ref=source.source_context_receipt_ref,
        skill_ref=original.skill_ref,
        attempt_id="validation-attempt",
    )
    inputs_ref = put(store, inputs, inputs.schema_version)
    assert isinstance(original.run.workload, ExecutionWorkload)
    plan = RunPlan.model_validate(
        original.run.model_copy(
            update={
                "run_id": "validation-run",
                "release_ref": release,
                "workload": original.run.workload.model_copy(
                    update={"task_inputs_ref": inputs_ref}
                ),
            }
        )
    )
    run = RunBinding(
        owner=source.run.owner.model_copy(
            update={
                "run_id": "validation-run",
                "job_id": "validation-job",
                "owner_id": "validation-owner",
            }
        ),
        release_ref=release,
        plan_ref=source.run.plan_ref,
        submission_key="validation-submission",
    )
    binding = SourceClaimBinding(
        scope_id=record.binding.scope_id, run=run, task=source.task
    )
    plan_ref = original.plans.publish(plan, operation(binding))
    binding = binding.model_copy(
        update={"run": run.model_copy(update={"plan_ref": plan_ref})}
    )
    validation = SourceStageValidation(
        parent=receipt, target_release_ref=release, authorization_ref=authorization
    )
    authority = UnitStageAuthority(validation, binding)
    claims = FileSourceStageValidations(
        root / "parent" / "claims",
        binding.scope_id,
        controls,
        store,
        original.plans,
        authority,
        validation=validation,
    )
    current = claims.claim(binding, operation(binding))
    origin = FrozenExecutionOrigin(
        validation=validation, parent_source_ref=original.source_ref
    )
    contexts = UnitHistoricalContext(parent)
    reader = OriginalExecutionTaskSource(
        original.plans, claims, contexts, original.source_reader.bindings, store
    )
    published = publish_execution_task_source(
        binding.run,
        current.reference,
        operation(binding),
        reader=reader,
        evidence=store,
        controls=controls,
        frozen_origin=origin,
    )
    op = parent.plan.operation.model_copy(
        update={
            "run_id": binding.run.owner.run_id,
            "owner_id": binding.run.owner.owner_id,
            "attempt_id": inputs.attempt_id,
        }
    )
    task = TaskExecutionPlan.model_validate(
        parent.plan.model_copy(
            update={
                "intent": published.source.intent,
                "source_ref": published.source_ref,
                "operation": op,
                "read_operation": operation(binding),
                "evaluation": parent.plan.evaluation.model_copy(
                    update={"attempt_id": inputs.attempt_id}
                ),
            }
        )
    )
    return FrozenSourceCase(
        parent,
        binding,
        origin,
        authority,
        claims,
        contexts,
        reader,
        published.source,
        published.source_ref,
        task,
    )
