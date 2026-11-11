"""Original task cleanup budget is distinct from component shutdown caps."""

from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .context_evidence import read_bytes


def require_frozen_task_cleanup_budget(
    plan: TaskExecutionPlan, evidence: EvidenceReader, control: OperationControl
) -> None:
    binding = plan.intent.binding.run
    if (
        binding.plan_ref.content_schema,
        binding.plan_ref.visibility,
        binding.plan_ref.media_type,
    ) != ("run-plan/3", "private", "application/json"):
        raise OwnershipConflict(
            "Original private frozen RunPlan required for cleanup budget"
        )
    original = RunPlan.model_validate_json(
        read_bytes(evidence, binding.plan_ref, 64 * 1024**2, control)
    )
    original.check_binding(binding)
    if plan.cleanup_seconds > original.resources.cleanup_timeout_seconds:
        raise OwnershipConflict("Task cleanup exceeds original frozen RunPlan budget")
