"""Read closed pre-attempt stage facts; never resume a historical resource."""

import hashlib
import json
from dataclasses import dataclass

from lab_generate_skill.adapters.slurm.accounting import (
    AccountingFact,
    parse_accounting,
)
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import ActorStepClosed
from lab_generate_skill.domain.claims import SourceClaimReceipt, SourceClaimRecord
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.run_plan import ExecutionWorkload, RunPlan
from lab_generate_skill.domain.stage_validation_admission import (
    ClosedPreAttemptStageEvidence,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .stage_parent import RetainedStageParentChecks
from lab_generate_skill.domain.closed_stage_acquisition import (
    ClosedPreRegistrationStageEvidence,
)
from .prior_acquisition_review import verify_pre_registration_failure
from .prior_preparation_review import EndedPreparationFacts, load_ended_preparation


@dataclass(frozen=True)
class ClosedPriorStageFacts:
    """Only immutable original facts; current authorization is never stored."""

    inputs: ClosedPreAttemptStageEvidence | ClosedPreRegistrationStageEvidence
    claim: SourceClaimRecord
    source: ExecutionTaskSource
    run: RunSnapshot
    plan: RunPlan
    resource: ResourceRecord
    session: EvidenceSessionSnapshot
    actor_closed: ActorStepClosed
    accounting: AccountingFact


class PriorStageReviewChecks:
    def __init__(self, parent: RetainedStageParentChecks) -> None:
        self.parent = parent
        self._facts: dict[
            EvidenceRef, ClosedPriorStageFacts | EndedPreparationFacts
        ] = {}

    def _load(
        self, reference: EvidenceRef, control: OperationControl
    ) -> ClosedPriorStageFacts | EndedPreparationFacts:
        if reference.content_schema == "ended-preparation-stage-evidence/1":
            return load_ended_preparation(self.parent, reference, control)
        reads = self.parent.reads
        inputs: ClosedPreAttemptStageEvidence | ClosedPreRegistrationStageEvidence
        if reference.content_schema == "closed-pre-registration-stage-evidence/1":
            inputs = reads.parse(
                reference,
                reference.content_schema,
                ClosedPreRegistrationStageEvidence,
                control,
            )
        else:
            inputs = reads.parse(
                reference,
                "closed-pre-attempt-stage-evidence/1",
                ClosedPreAttemptStageEvidence,
                control,
            )
        claim = reads.parse(
            inputs.claim_ref, "source-claim/1", SourceClaimRecord, control
        )
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
            source.schema_version != "execution-task-source/2"
            or source.frozen_origin is None
            or claim.binding.run != source.run
            or claim.binding.task != source.task
            or source.intent.binding.claim_ref != inputs.claim_ref
            or snapshot.binding != source.run
            or run.stage != "sealed"
            or run.stop_reason != "error"
            or (attempts and isinstance(inputs, ClosedPreAttemptStageEvidence))
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
            raise OwnershipConflict(
                "Prior stage is not a known failed pre-attempt Actor run"
            )
        diagnostic = json.loads(reads.read(inputs.diagnostic_ref, control))
        if (
            diagnostic.get("schema_version") != "current-run-close/1"
            or diagnostic.get("run") != source.run.model_dump(mode="json")
            or diagnostic.get("attempt_stages")
            != {a.binding.attempt_id: a.stage for a in attempts}
            or not isinstance(diagnostic.get("error"), dict)
            or diagnostic.get("physical_close_or_safe_reset_grant") is not False
            or inputs.diagnostic_ref not in run.events[-1].outputs
        ):
            raise OwnershipConflict(
                "Prior stage error/closure diagnostic changed its run"
            )
        session = reads.parse(
            inputs.session_ref,
            "evidence-session-snapshot/3",
            EvidenceSessionSnapshot,
            control,
        )
        if (
            session.binding.owner != source.run.owner
            or not session.entries
            or any(
                entry.outcome is None
                or entry.outcome.status != "succeeded"
                or not entry.reusable
                for entry in session.entries
            )
        ):
            raise OwnershipConflict(
                "Prior stage has unresolved or unsuccessful metadata work"
            )
        resource = reads.parse(
            inputs.actor_resource_ref, "resource-record/2", ResourceRecord, control
        )
        if (
            resource.state != "closed"
            or resource.token.owner != source.run.owner
            or resource.token.resource_kind != "actor"
            or resource.token.scope != "batch"
            or resource.token.attempt_id is not None
        ):
            raise OwnershipConflict("Prior stage lacks its original closed batch Actor")
        self.parent.verify_closed_resource(resource, control)
        intent = reads.parse(
            resource.events[1].evidence[0],
            "resource-acquisition-intent/1",
            ResourceAcquisitionIntent,
            control,
        )
        spec = reads.parse(
            intent.configuration_ref,
            "actor-resource-spec/1",
            ActorResourceSpec,
            control,
        )
        closed_fact = json.loads(reads.read(resource.events[-1].evidence[0], control))
        closed = ActorStepClosed.model_validate_json(
            json.dumps(closed_fact["step_closed"])
        )
        if (
            spec.token != resource.token
            or spec.release_ref != source.run.release_ref
            or spec.model_binding_ref != plan.models[0].model_binding_ref
            or closed.target.execution != spec.slurm.allocation.facts.execution
        ):
            raise OwnershipConflict(
                "Prior Actor closure changed original model/execution"
            )
        accounting = parse_accounting(
            reads.read(inputs.accounting_ref, control), closed.target.execution
        )
        if (
            accounting.state != "FAILED"
            or accounting.ended_at_epoch is None
            or accounting.exit_status == 0
            or accounting.exit_signal != 0
        ):
            raise OwnershipConflict(
                "Prior job is not an explicitly failed original execution"
            )
        if isinstance(inputs, ClosedPreRegistrationStageEvidence):
            verify_pre_registration_failure(reads, inputs, source, snapshot, control)
        return ClosedPriorStageFacts(
            inputs, claim, source, snapshot, plan, resource, session, closed, accounting
        )

    def verify_peer(
        self,
        record: SourceClaimRecord,
        raw: bytes,
        references: tuple[EvidenceRef, ...],
        current: RunBinding,
        control: OperationControl,
    ) -> EvidenceRef:
        """Fresh canonical peer/current binding joins over retained closed facts."""
        control.checkpoint()
        candidates: list[
            tuple[EvidenceRef, ClosedPriorStageFacts | EndedPreparationFacts]
        ] = []
        for reference in references:
            facts = self._facts.get(reference)
            if facts is None:
                facts = self._load(reference, control)
                self._facts[reference] = facts
            if facts.inputs.claim_ref.sha256 == hashlib.sha256(raw).hexdigest():
                candidates.append((reference, facts))
        if len(candidates) != 1:
            raise OwnershipConflict(
                "Prior canonical stage requires one exact closed review"
            )
        reference, facts = candidates[0]
        origin = facts.source.frozen_origin
        assert origin is not None
        run, attempts = facts.run.project()
        if (
            facts.claim != record
            or (
                not isinstance(facts, EndedPreparationFacts)
                and (
                    run.stage != "sealed"
                    or (
                        attempts
                        and isinstance(facts.inputs, ClosedPreAttemptStageEvidence)
                    )
                    or facts.resource.state != "closed"
                    or any(not entry.reusable for entry in facts.session.entries)
                )
            )
            or facts.accounting.state != "FAILED"
            or record.binding.scope_id != self.parent.binding.scope_id
            or record.binding.task != self.parent.binding.task
            or origin.validation.parent != self.parent.origin.validation.parent
            or origin.parent_source_ref != self.parent.origin.parent_source_ref
            or origin.validation.stage_scope
            != self.parent.origin.validation.stage_scope
            or record.binding.run.release_ref == current.release_ref
            or record.binding.run.owner == current.owner
            or record.binding.run.owner.job_id == current.owner.job_id
            or record.binding.run.owner.run_id == current.owner.run_id
        ):
            raise OwnershipConflict(
                "Prior stage review changed task/parent or replayed its owner"
            )
        control.checkpoint()
        return reference
