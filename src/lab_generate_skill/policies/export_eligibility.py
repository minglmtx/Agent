"""Evidence-independent eligibility rules; the actual admission port is separate."""

from lab_generate_skill.domain.export import ExportPlan, ExportScope, ExportAdmission
from lab_generate_skill.domain.export_material import ExportMaterial


def rejection(
    plan: ExportPlan,
    scope: ExportScope,
    material: ExportMaterial,
    admission: ExportAdmission,
) -> str | None:
    q = material.qualification
    if material.current.status != "verified":
        return "review_not_verified"
    if (
        material.current.plan.selection.status != "accepted"
        or material.selected_skill is None
        or material.selected_task is None
    ):
        return "no_positive_target"
    if admission.status != "eligible":
        return admission.reason_code
    if q.kind != plan.kind or scope.kind != plan.kind:
        return "qualification_kind_mismatch"
    if material.selected_task.evaluation.scope not in scope.allowed_evaluation_scopes:
        return "evaluation_scope_not_allowed"
    if plan.kind == "formal":
        if (
            material.run_plan.purpose != "training"
            or not q.labels.formal()
            or material.selected_task.evaluation.scope == "engineering"
        ):
            return "formal_training_qualification_required"
    elif q.labels.training_data or (
        q.labels.output_purpose,
        q.labels.target_status,
        q.labels.teacher_mode,
    ) != ("engineering", "interface_verified", "fixture"):
        return "fixture_must_remain_nontraining"
    return None
