"""Construction byte/content checks, separate from file transaction mechanics.

Known schemas are parsed and compared, not merely hashed: RunPlan membership,
PublicTask/context, sampled input, and Evaluation. Provider-specific responses,
attempt closure and authority semantics remain mandatory trusted hooks.
"""

from lab_generate_skill.domain.construction import (
    AttemptPlanned,
    AttemptCompleted,
    AttemptResolved,
    CallPlanned,
    CallCompleted,
    ConstructionPlan,
    ProgressEvent,
)
from lab_generate_skill.adapters.plans.observations import ObservationReader
from lab_generate_skill.adapters.plans.construction_generation import (
    ConstructionGenerationReader,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.construction_retrieval import (
    ConstructionRetrievalReader,
)
from .construction_actor_capabilities import selected_actor_capabilities
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.domain.construction_inputs import (
    PublicConstructionContext,
    RevisionInput,
    RevisionResult,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.construction import ConstructionAuthority
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier


class ConstructionEvidence:
    def __init__(
        self,
        evidence: EvidenceReader,
        plans: RunPlans,
        authority: ConstructionAuthority,
        contexts: ContextRecords,
        retrieval: RetrievalRecords,
        claims: SourceClaims,
        teacher_review: TeacherConstructionVerifier | None = None,
    ) -> None:
        self.evidence, self.plans, self.authority = evidence, plans, authority
        self.teacher_review = teacher_review
        self.contexts = contexts
        self.claims = claims
        self.reads = StateReads(evidence)
        self.retrieval = ConstructionRetrievalReader(evidence, retrieval)

    def _read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        raw = self.evidence.read(reference, control=control)
        control.checkpoint()
        return raw

    def _refs(self, value: object, control: OperationControl) -> None:
        for reference in dict.fromkeys(evidence_references(value)):
            self._read(reference, control)

    def _qualified_context(
        self, plan: ConstructionPlan, op: OperationContext, control: OperationControl
    ) -> None:
        """Bind qualified source to the exact frozen private task, not just its ID."""
        qualified = self.contexts.load_context(plan.context_receipt_ref, op)
        if (
            qualified.public_context_ref != plan.public_context_ref
            or qualified.scope.task != plan.task.identity
            or qualified.spec_ref != plan.task.baseline_ref
            or (qualified.scope.owner.run_id, qualified.scope.owner.owner_id)
            != (plan.run.owner.run_id, plan.run.owner.owner_id)
        ):
            raise OwnershipConflict(
                "Qualified source differs from the construction plan"
            )
        baseline = self.reads.parse(
            qualified.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
        )
        prepared = self.reads.parse(
            baseline.prepared_ref, "prepared-task/1", PreparedTask, control
        )
        binding = self.reads.parse(
            prepared.task_binding_ref, "task-binding/1", TaskBinding, control
        )
        if binding != plan.task:
            raise OwnershipConflict(
                "Qualified source has a different private task binding"
            )
        control.checkpoint()

    def _claimed_source(
        self, plan: ConstructionPlan, op: OperationContext, control: OperationControl
    ) -> None:
        control.checkpoint()
        record = self.claims.require_source(plan.claim_ref, plan.run, plan.task, op)
        check_source_claim(record, plan.claim_ref, plan.run, plan.task)
        control.checkpoint()

    def plan(
        self, plan: ConstructionPlan, op: OperationContext, control: OperationControl
    ) -> None:
        loaded = self.plans.load(plan.run, op)
        expected = ConstructionPlan.from_run_plan(
            loaded,
            plan.run,
            plan.task.identity.task_id,
            claim_ref=plan.claim_ref,
            public_context_ref=plan.public_context_ref,
            context_receipt_ref=plan.context_receipt_ref,
            retrieval_ref=plan.retrieval_ref,
            retrieval_scope=plan.retrieval_scope,
            actor_context_configuration_ref=plan.actor_context_configuration_ref,
        )
        if expected != plan:
            raise OwnershipConflict("Construction differs from its stored RunPlan")
        self._claimed_source(plan, op, control)
        self._refs(plan, control)
        selected_actor_capabilities(plan, self.reads, control)
        context = PublicConstructionContext.model_validate_json(
            self._read(plan.public_context_ref, control)
        )
        task = PublicTask.model_validate_json(
            self._read(plan.task.public_task_ref, control)
        )
        if context.task != task or task.identity != plan.task.identity:
            raise OwnershipConflict("Public context/task differs from frozen source")
        ObservationReader(self.evidence).initial(context, control)
        self._qualified_context(plan, op, control)
        self.retrieval.load(plan, op, control)
        self.authority.verify_plan(plan, op)
        control.checkpoint()

    def event(
        self,
        progress: ConstructionProgress,
        event: ProgressEvent,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        if isinstance(event, (CallPlanned, AttemptPlanned)):
            self._claimed_source(progress.plan, op, control)
            self._qualified_context(progress.plan, op, control)
        self._refs(event, control)
        if isinstance(event, CallPlanned):
            call = event.call
            if call.role == "generator":
                ConstructionGenerationReader(self.evidence, self.retrieval).load(
                    progress.plan, call, op, control
                )
            else:
                revision = RevisionInput.model_validate_json(
                    self._read(call.input_ref, control)
                )
                self._refs(revision, control)
                if (revision.request_id, revision.teacher_round, revision.seed) != (
                    call.request_id,
                    call.candidate_slot - 3,
                    call.seed,
                ):
                    raise OwnershipConflict(
                        "Actual Teacher input differs from registered call"
                    )
        if isinstance(event, (AttemptCompleted, AttemptResolved)):
            actual = Evaluation.model_validate_json(
                self._read(event.result.evaluation_ref, control)
            )
            if actual != event.result.evaluation:
                raise OwnershipConflict(
                    "Inline judgment differs from persisted Evaluation"
                )
        if (
            isinstance(event, CallCompleted)
            and isinstance(event.response, RevisionResult)
            and event.response.schema_version == "revision-result/2"
        ):
            if self.teacher_review is None:
                raise OwnershipConflict(
                    "Teacher v2 construction commit requires its original readonly proof verifier"
                )
            self.teacher_review.verify_construction(
                progress, event, op, control=control
            )
        self.authority.verify_event(progress, event, op)
        control.checkpoint()
