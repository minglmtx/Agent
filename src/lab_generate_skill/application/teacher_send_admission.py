"""Original live construction/claim/paid-request facts at Teacher send admission.

Read-only gate before reserve; the original ledger still atomically dispatches
once. Snapshot rechecks detect in-check changes, not a world lock after return.
The required original authority retains actual provider/config/count/fee/writer
and exclusivity checks throughout the actual call. No grant is inferred here.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    CallPlanned,
    CallUncertain,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.generation import RequestRecord
from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.teacher_revision import BoundTeacherRevisionPlan
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OwnershipConflict,
    InvalidTransition,
    RevisionConflict,
    DispatchAlreadyCommitted,
)
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.model import ModelSendAuthority
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.teacher_revision import TeacherRevisionPlans


@dataclass(frozen=True)
class TeacherSendAdmissionDeps:
    construction: ConstructionJournal
    runs: RunJournal
    claims: SourceClaims
    run_plans: RunPlans
    requests: RequestLedger
    original: ModelSendAuthority


class ConstructionTeacherSendAuthority:
    def __init__(
        self,
        run: RunBinding,
        plans: TeacherRevisionPlans,
        deps: TeacherSendAdmissionDeps,
        controls: OperationControls,
    ) -> None:
        if any(
            v is None
            for v in (
                plans,
                controls,
                deps.construction,
                deps.runs,
                deps.claims,
                deps.run_plans,
                deps.requests,
                deps.original,
            )
        ):
            raise ValueError(
                "Original Teacher/run/claim/request/provider authorities required"
            )
        self.run = RunBinding.model_validate(run)
        self.plans, self.deps, self.controls = plans, deps, controls

    def verify(self, plan: ModelSendPlan, request: ResolvedModelRequest) -> None:
        plan = ModelSendPlan.model_validate(plan)
        request = ResolvedModelRequest.model_validate(request)
        identity = plan.reservation.request
        if (
            request.request != identity
            or request.limits != plan.limits
            or identity.role != "teacher"
        ):
            raise OwnershipConflict("Teacher send changed original request/role/limits")
        for op in (plan.reserve_operation, plan.operation, plan.settlement_operation):
            if (
                op.run_id,
                op.owner_id,
                op.attempt_id,
                op.allocation_id,
                op.recovery_ref,
            ) != (self.run.owner.run_id, self.run.owner.owner_id, None, None, None):
                raise OwnershipConflict(
                    "Teacher send requires original run-level operations"
                )
        control = self.controls.bind(plan.operation)
        control.checkpoint()
        self.deps.original.verify(plan, request)
        control.checkpoint()
        bound = BoundTeacherRevisionPlan.model_validate(
            self.plans.load(identity.request_id, plan.operation, control=control)
        )
        if bound.plan.send != plan:
            raise OwnershipConflict("Teacher send substituted immutable original plan")
        progress = ConstructionProgress.model_validate(
            self.deps.construction.read(plan.operation)
        )
        snapshot = RunSnapshot.model_validate(self.deps.runs.read(plan.operation))
        if progress.plan.run != self.run or snapshot.binding != self.run:
            raise OwnershipConflict(
                "Teacher journals differ from original complete run binding"
            )
        run, _ = snapshot.project()
        if run.stage != "running" or run.stop_reason is not None:
            raise InvalidTransition("Teacher send requires unstopped running run")
        view = progress.project()
        if (
            view.pending_call != bound.plan.call
            or view.next_action.kind != "await_response"
        ):
            raise InvalidTransition("No original pending Teacher call eligible to send")
        if any(
            isinstance(e, CallUncertain) and e.request_id == identity.request_id
            for e in progress.events
        ):
            raise DispatchAlreadyCommitted(
                "Original uncertain Teacher call cannot renew"
            )
        registrations = [
            e
            for e in progress.events
            if isinstance(e, CallPlanned) and e.call.request_id == identity.request_id
        ]
        if len(registrations) != 1 or registrations[0].operation != plan.operation:
            raise OwnershipConflict(
                "Teacher send changed original registration operation"
            )
        teacher = bound.plan
        if (teacher.preparation.scope.owner, teacher.preparation.scope.task) != (
            self.run.owner,
            progress.plan.task.identity,
        ) or teacher.call.seed != progress.plan.method.teacher_seed(
            teacher.revision.teacher_round
        ):
            raise OwnershipConflict("Teacher send changed original task/method")
        frozen = self.deps.run_plans.load(self.run, plan.operation)
        expected = ConstructionPlan.from_run_plan(
            frozen,
            self.run,
            progress.plan.task.identity.task_id,
            claim_ref=progress.plan.claim_ref,
            public_context_ref=progress.plan.public_context_ref,
            context_receipt_ref=progress.plan.context_receipt_ref,
            retrieval_ref=progress.plan.retrieval_ref,
            retrieval_scope=progress.plan.retrieval_scope,
            actor_context_configuration_ref=progress.plan.actor_context_configuration_ref,
        )
        if expected != progress.plan or frozen.budget is None:
            raise OwnershipConflict("Teacher send differs from original paid RunPlan")
        model = next(m for m in frozen.models if m.role == "teacher")
        role = next(r for r in frozen.budget.roles if r.role == "teacher")
        profile = teacher.preparation.profile
        if (
            (
                model.provider,
                model.model,
                model.paid,
                model.model_binding_ref,
                model.parameters_ref,
            )
            != (
                profile.provider,
                profile.model,
                profile.paid,
                teacher.call.model_binding_ref,
                teacher.call.base_parameters_ref,
            )
            or (plan.reservation.scope.authorization, plan.reservation.scope.budget_id)
            != (frozen.budget.authorization, role.budget_id)
            or plan.reservation.ceiling.units > role.reservation_ceiling.units
        ):
            raise OwnershipConflict(
                "Teacher send changed original model/authorization/subbudget/ceiling"
            )
        claim = self.deps.claims.require_source(
            progress.plan.claim_ref, self.run, progress.plan.task, plan.operation
        )
        check_source_claim(claim, progress.plan.claim_ref, self.run, progress.plan.task)
        # Missing reservation is only absence, never authority. Provider/writer,
        # source, full input and atomic budget/dispatch still independently gate.
        record: RequestRecord | None
        try:
            record = RequestRecord.model_validate(
                self.deps.requests.read(identity, plan.operation)
            )
        except EvidenceNotFound:
            record = None
        if record is not None:
            if (
                record.reservation != plan.reservation
                or record.events[0].operation_id != plan.reserve_operation.operation_id
            ):
                raise OwnershipConflict("Original Teacher reservation changed")
            if any(e.state == "dispatching" for e in record.events):
                raise DispatchAlreadyCommitted(
                    "Original Teacher dispatch/outcome cannot resend"
                )
            if record.state != "budget_reserved" or record.revision != 0:
                raise InvalidTransition(
                    "Original closed Teacher reservation cannot renew"
                )
        control.checkpoint()
        self.deps.original.verify(plan, request)
        check_source_claim(
            self.deps.claims.require_source(
                progress.plan.claim_ref, self.run, progress.plan.task, plan.operation
            ),
            progress.plan.claim_ref,
            self.run,
            progress.plan.task,
        )
        if (
            ConstructionProgress.model_validate(
                self.deps.construction.read(plan.operation)
            )
            != progress
            or RunSnapshot.model_validate(self.deps.runs.read(plan.operation))
            != snapshot
        ):
            raise RevisionConflict(
                "Original journals changed during Teacher send admission"
            )
        control.checkpoint()
