"""Run-plan admission for the existing resource protocol, not a launch permit.

Checks actual plan/model evidence and live run state before start and handoff.
The mandatory underlying authority still verifies deployment/Slurm ownership
and original resource closure. This decorator cannot replace that authority,
first resource acquisition acknowledgement, or per-request construction checks.
"""

import hashlib
import os
import threading
from dataclasses import dataclass

from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.generator_model_binding import GeneratorModelBinding
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_step import (
    GeneratorStepCleanup,
    GeneratorStepStarted,
    GeneratorStepClosed,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.run_plan import RunPlan, ConstructionWorkload
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.generator_resources import GeneratorResourceAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans


@dataclass(frozen=True)
class GeneratorResourceAdmissionDeps:
    plans: RunPlans
    runs: RunJournal
    evidence: EvidenceReader
    execution: GeneratorResourceAuthority


class RunGeneratorResourceAuthority:
    def __init__(self, run: RunBinding, deps: GeneratorResourceAdmissionDeps) -> None:
        self._run, self._deps = RunBinding.model_validate(run), deps
        self._context = (os.getpid(), threading.get_ident())
        self._accepted: tuple[GeneratorResourceSpec, OperationContext] | None = None

    def _scope(
        self,
        spec: GeneratorResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Resource admission belongs to another execution context"
            )
        token = spec.token
        if token.owner != self._run.owner or spec.release_ref != self._run.release_ref:
            raise OwnershipConflict(
                "Generator resource differs from original run/release"
            )
        if (
            op.run_id,
            op.owner_id,
            op.allocation_id,
            op.attempt_id,
            op.recovery_ref,
        ) != (
            token.owner.run_id,
            token.owner.owner_id,
            token.allocation_id,
            token.attempt_id,
            token.recovery_ref,
        ):
            raise OwnershipConflict(
                "Resource operation differs from original allocation"
            )

    def _live(
        self,
        spec: GeneratorResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> tuple[RunPlan, RunSnapshot]:
        self._scope(spec, op, control)
        if op.mode != "execute" or op.parent_operation_id is not None:
            raise OwnershipConflict(
                "Resource start requires its independent execute operation"
            )
        plan = RunPlan.model_validate(self._deps.plans.load(self._run, op))
        plan.check_binding(self._run)
        snapshot = RunSnapshot.model_validate(self._deps.runs.read(op))
        if snapshot.binding != self._run or snapshot.capacity != plan.run_capacity:
            raise OwnershipConflict("Resource run journal differs from frozen plan")
        run, _ = snapshot.project()
        if run.stage != "running" or run.stop_reason is not None:
            raise InvalidTransition(
                "Generator resource requires an unstopped running run"
            )
        if not isinstance(plan.workload, ConstructionWorkload):
            raise InvalidTransition("Run workload does not use a Generator resource")
        model = next(m for m in plan.models if m.role == "generator")
        if (
            model.paid
            or model.provider != "transformers"
            or model.model_binding_ref != spec.model_binding_ref
        ):
            raise OwnershipConflict(
                "Generator resource differs from planned local model"
            )
        ref = spec.model_binding_ref
        if ref.size_bytes > 16384:
            raise EvidenceIntegrityError(
                "Generator model binding exceeds its read budget"
            )
        control.checkpoint()
        raw = self._deps.evidence.read(ref, control=control)
        control.checkpoint()
        if len(raw) != ref.size_bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise EvidenceIntegrityError(
                "Generator model binding bytes differ from reference"
            )
        binding = GeneratorModelBinding.model_validate_json(raw)
        if (binding.model, binding.provider, binding.release_ref) != (
            model.model,
            model.provider,
            spec.release_ref,
        ):
            raise OwnershipConflict(
                "Actual Generator model label/provider/release differs from plan"
            )
        control.checkpoint()
        return plan, snapshot

    def _unchanged(
        self,
        before: tuple[RunPlan, RunSnapshot],
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        after = (
            RunPlan.model_validate(self._deps.plans.load(self._run, op)),
            RunSnapshot.model_validate(self._deps.runs.read(op)),
        )
        if after != before:
            raise RevisionConflict(
                "Run plan or journal changed during resource admission"
            )
        control.checkpoint()

    def authorize_start(
        self,
        spec: GeneratorResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        spec, op = GeneratorResourceSpec.model_validate(
            spec
        ), OperationContext.model_validate(op)
        if self._accepted is not None and self._accepted != (spec, op):
            raise OwnershipConflict(
                "Resource authority cannot change original acquisition"
            )
        before = self._live(spec, op, control)
        self._deps.execution.authorize_start(spec, op, control)
        self._unchanged(before, op, control)
        self._accepted = (spec, op)

    def verify_started(
        self,
        spec: GeneratorResourceSpec,
        started: GeneratorStepStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        spec, op = GeneratorResourceSpec.model_validate(
            spec
        ), OperationContext.model_validate(op)
        started = GeneratorStepStarted.model_validate(started)
        if self._accepted != (spec, op):
            raise OwnershipConflict("Worker handoff has no original resource admission")
        before = self._live(spec, op, control)
        self._deps.execution.verify_started(spec, started, op, control)
        self._unchanged(before, op, control)

    def verify_closed(
        self,
        spec: GeneratorResourceSpec,
        cleanup: GeneratorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> GeneratorStepClosed | None:
        spec, op = GeneratorResourceSpec.model_validate(
            spec
        ), OperationContext.model_validate(op)
        self._scope(spec, op, control)
        if (
            self._accepted is None
            or self._accepted[0] != spec
            or (
                op.mode != "cleanup"
                or op.parent_operation_id != self._accepted[1].operation_id
            )
        ):
            raise OwnershipConflict("Cleanup must retain original admitted acquisition")
        cleanup = GeneratorStepCleanup.model_validate(cleanup)
        # Do not read plan/run here: stopping or losing dependencies cannot forbid
        # verification of the original physical cleanup.
        closed = self._deps.execution.verify_closed(
            spec, cleanup, termination, op, control
        )
        control.checkpoint()
        return None if closed is None else GeneratorStepClosed.model_validate(closed)
