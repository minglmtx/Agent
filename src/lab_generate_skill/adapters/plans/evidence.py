"""CAS-backed RunPlan producer/consumer, without current-directory discovery.

Validates direct input evidence and deterministic capacity on both boundaries.
Transitive release/split/model/claim/authorization semantics remain their own
admission checks; a successfully loaded plan is not permission to run it.
"""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.run_plan import RunPlanInputChecks
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls


def check_run_plan_input_evidence(
    plan: RunPlan, store: EvidenceStore, control: OperationControl
) -> None:
    """Original full direct-input checks, also used inside the fixed reader."""
    for reference in plan.references():
        control.checkpoint()
        store.read(reference, control=control)
        control.checkpoint()


class EvidenceRunPlans:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        *,
        input_checks: RunPlanInputChecks | None = None,
    ) -> None:
        self._store = store
        self._controls = controls
        self._input_checks = input_checks

    def _inputs(
        self, plan: RunPlan, op: OperationContext, control: OperationControl
    ) -> None:
        control.checkpoint()
        if self._input_checks is None:
            check_run_plan_input_evidence(plan, self._store, control)
        else:
            self._input_checks.verify_inputs(plan, op, control)
        control.checkpoint()

    def publish(self, plan: RunPlan, op: OperationContext) -> EvidenceRef:
        plan = RunPlan.model_validate(plan)
        op = OperationContext.model_validate(op)
        control = self._controls.bind(op)
        control.checkpoint()
        if (
            op.run_id != plan.run_id
            or op.attempt_id is not None
            or op.mode != "execute"
        ):
            raise OwnershipConflict(
                "Plan publication requires its run-level execute operation"
            )
        self._inputs(plan, op, control)
        reference = self._store.put(
            plan.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="run-plan/3",
                visibility="private",
                producer="run-plans-v1",
            ),
            control=control,
        )
        control.checkpoint()
        return reference

    def load(self, binding: RunBinding, op: OperationContext) -> RunPlan:
        binding = RunBinding.model_validate(binding)
        op = OperationContext.model_validate(op)
        control = self._controls.bind(op)
        control.checkpoint()
        if (op.run_id, op.owner_id) != (
            binding.owner.run_id,
            binding.owner.owner_id,
        ) or op.attempt_id is not None:
            raise OwnershipConflict("Plan loading must address its run and owner")
        if (
            binding.plan_ref.content_schema != "run-plan/3"
            or binding.plan_ref.visibility != "private"
        ):
            raise ValueError("Unsupported plan payload or visibility")
        plan = RunPlan.model_validate_json(
            self._store.read(binding.plan_ref, control=control)
        )
        plan.check_binding(binding)
        control.checkpoint()
        self._inputs(plan, op, control)
        return plan
