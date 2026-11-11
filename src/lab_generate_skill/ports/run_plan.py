"""Frozen plan transport; publishing or loading grants no execution authority."""

from typing import Protocol

from lab_generate_skill.ports.lifecycle import OperationControl

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan


class RunPlans(Protocol):
    def publish(self, plan: RunPlan, op: OperationContext) -> EvidenceRef: ...

    def load(self, binding: RunBinding, op: OperationContext) -> RunPlan: ...


class RunPlanInputChecks(Protocol):
    """Check every direct immutable input now; never a run permission."""

    def verify_inputs(
        self, plan: RunPlan, op: OperationContext, control: OperationControl
    ) -> None: ...
