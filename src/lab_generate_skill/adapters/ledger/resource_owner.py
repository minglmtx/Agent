"""Current original claimed run/physical caller for concrete resource suppliers.

This joins existing claim/run/plan and neutral task-source readers. No second journal, cached permit,
resource creation or external action. Cleanup ownership is independent of the
permission to dispatch new work on a running run.
"""

from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.adapters.operation_progress import operation_stage
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.ports.claims import SourceClaims, SourceClaimBodyChecks
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.resource_owner import OriginalRunResourceAccess
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseRunSources,
    TaskPhaseOwnershipReads,
)


class ClaimedRunResourceOwner:
    def __init__(
        self,
        authority: OriginalRunResourceAccess,
        claim_ref: EvidenceRef,
        read: OperationContext,
        *,
        claims: SourceClaims,
        runs: RunJournal,
        plans: RunPlans,
        evidence: EvidenceStore,
        task_plan: TaskExecutionPlan,
        sources: TaskPhaseSources,
        source_run_reads: TaskPhaseRunSources | None = None,
    ) -> None:
        if authority is None or not callable(
            getattr(authority, "require_caller", None)
        ):
            raise TypeError("Actual original Slurm claim caller access required")
        self.authority, self.claim_ref, self.read = (
            authority,
            claim_ref,
            OperationContext.model_validate(read),
        )
        self.claims, self.runs, self.plans, self.evidence = (
            claims,
            runs,
            plans,
            evidence,
        )
        if any(v is None for v in (claims, runs, plans, evidence)):
            raise TypeError("Original persistent ownership/run/plan/evidence required")
        self.run, self.task = authority.run, authority.task
        self.task_plan, self.sources = (
            TaskExecutionPlan.model_validate(task_plan),
            sources,
        )
        if (
            sources is None
            or self.task_plan.intent.binding.run != self.run
            or self.task_plan.intent.binding.task != self.task.identity
            or self.task_plan.intent.binding.claim_ref != claim_ref
        ):
            raise OwnershipConflict(
                "Resource owner changed original task/claim/source binding"
            )
        if source_run_reads is not None and source_run_reads is not sources:
            raise OwnershipConflict("Same source reader must supply same-call RunPlan")
        self.source_run_reads = source_run_reads
        self.reads = StateReads(evidence)
        if (
            read.run_id,
            read.owner_id,
            read.attempt_id,
            read.allocation_id,
            read.recovery_ref,
        ) != (self.run.owner.run_id, self.run.owner.owner_id, None, None, None):
            raise OwnershipConflict("Original run-level ownership reader required")

    def caller(self, operation: OperationContext, control: OperationControl) -> None:
        control.checkpoint()
        self.authority.require_caller(operation)
        control.checkpoint()

    def require(
        self, operation: OperationContext, control: OperationControl, *, new_work: bool
    ) -> RunPlan:
        return self._require(operation, control, new_work=new_work)[0]

    def _require(
        self,
        operation: OperationContext,
        control: OperationControl,
        *,
        new_work: bool,
        need_source: bool = False,
    ) -> tuple[RunPlan, TaskPhaseSourceState | None]:
        # Pass exact immutable source bodies; every invocation still reads the
        # current claim ledger, running journal, caller and storage authority.
        operation = OperationContext.model_validate(operation)
        control.checkpoint()
        if (operation.run_id, operation.owner_id) != (
            self.run.owner.run_id,
            self.run.owner.owner_id,
        ):
            raise OwnershipConflict("Resource caller changed original run/owner")
        self.authority.require_caller(operation)
        read = read_operation(self.read, operation)
        owned = None
        if isinstance(self.source_run_reads, TaskPhaseOwnershipReads) and isinstance(
            self.claims, SourceClaimBodyChecks
        ):
            with operation_stage("owner.task-source-and-plan"):
                owned = self.source_run_reads.read_ownership(
                    self.task_plan, read, control
                )
        if owned is not None and owned[2].reference != self.claim_ref:
            raise OwnershipConflict(
                "Resource source changed original claim body reference"
            )
        with operation_stage("owner.current-claim"):
            if owned is not None and isinstance(self.claims, SourceClaimBodyChecks):
                record = self.claims.require_source_verified(
                    owned[2], self.run, self.task, read
                )
            else:
                record = self.claims.require_source(
                    self.claim_ref, self.run, self.task, read
                )
        check_source_claim(record, self.claim_ref, self.run, self.task)
        self.authority.require_caller(read)
        source = None
        if owned is not None:
            source, plan, _ = owned
            require_complete_bytes(self.run.plan_ref, plan.model_dump_json().encode())
            plan.check_binding(self.run)
            self.authority.require_caller(read)
        elif (new_work or need_source) and self.source_run_reads is not None:
            with operation_stage("owner.task-source-and-plan"):
                source, plan = self.source_run_reads.read_with_run(
                    self.task_plan, read, control
                )
            # This exact immutable plan was checked in this synchronous source
            # call. It is never retained for the next resource/side effect.
            require_complete_bytes(self.run.plan_ref, plan.model_dump_json().encode())
            plan.check_binding(self.run)
            self.authority.require_caller(read)
        else:
            with operation_stage("owner.run-plan"):
                plan = self.plans.load(self.run, read)
        with operation_stage("owner.run-journal"):
            snapshot = self.runs.read(read)
        if snapshot.binding != self.run or self.task not in plan.tasks:
            raise OwnershipConflict("Resource owner changed original frozen execution")
        state, _ = snapshot.project()
        if new_work and (
            operation.mode != "execute"
            or state.stage != "running"
            or state.stop_reason is not None
        ):
            raise InvalidTransition(
                "Stopped original run cannot start new resource work"
            )
        if new_work and source is None:
            with operation_stage("owner.task-source"):
                source = self.sources.read(self.task_plan, read, control)
        if source is not None and (
            source.intent != self.task_plan.intent or source.task != self.task
        ):
            raise OwnershipConflict("New resource work changed original current source")
        control.checkpoint()
        return plan, source

    def task_source(
        self, operation: OperationContext, control: OperationControl
    ) -> TaskPhaseSourceState:
        _, source = self._require(
            operation, control, new_work=operation.mode == "execute", need_source=True
        )
        if source is None:
            source = self.sources.read(
                self.task_plan, read_operation(self.read, operation), control
            )
        if source.intent != self.task_plan.intent or source.task != self.task:
            raise OwnershipConflict("Resource changed original current task source")
        self.authority.require_caller(operation)
        control.checkpoint()
        return source

    def model(
        self,
        spec: ActorResourceSpec,
        operation: OperationContext,
        control: OperationControl,
        *,
        new_work: bool,
    ) -> None:
        spec = ActorResourceSpec.model_validate(spec)
        plan = self.require(operation, control, new_work=new_work)
        actors = tuple(role for role in plan.models if role.role == "actor")
        if len(actors) != 1:
            raise OwnershipConflict("Exactly one original Actor role required")
        role = actors[0]
        model = self.reads.parse(
            role.model_binding_ref, "model-binding/1", ActorModelBinding, control
        )
        release = self.reads.parse(
            self.run.release_ref, "release-manifest/1", ReleaseManifest, control
        )
        artifacts = tuple(
            a for a in release.artifacts if a.artifact_id == model.model_artifact_id
        )
        if (
            spec.token.owner != self.run.owner
            or spec.slurm.allocation.facts.execution != self.authority.execution
            or spec.slurm.allocation.facts.cgroup != self.authority.controller
            or spec.release_ref != self.run.release_ref
            or spec.model_binding_ref != role.model_binding_ref
            or role.role != "actor"
            or role.paid
            or model.release_ref != self.run.release_ref
            or model.model != role.model
            or len(artifacts) != 1
            or spec.artifact.artifact_id != model.model_artifact_id
            or spec.artifact.files != artifacts[0].files
            or self.reads.read(model.engine_config_ref, control)
            != spec.engine_config.model_dump_json().encode()
        ):
            raise OwnershipConflict(
                "Model resource changed actual frozen source/release/owner"
            )
