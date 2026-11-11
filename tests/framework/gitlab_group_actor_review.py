"""Independent readonly original Group oracle; never a live source authority."""

import json
from typing import Any
from lab_generate_skill.bootstrap.gitlab_group_evaluation import gitlab_group_evaluator
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.evidence_schema import GroupEvidence
from lab_generate_skill.sites.gitlab.group_evaluation_reads import GroupEvaluationReads
from test_gitlab_group_rules import GROUP, GUARD


def review_group_judgment(
    contract: EvaluationContract,
    selected: GroupEvidence,
    saved: Evaluation,
    store: EvidenceReader,
    control: OperationControl,
) -> dict[str, Any]:
    current = gitlab_group_evaluator(selected).evaluate(contract, store, control)
    if current != saved:
        raise EvidenceIntegrityError("Independent Group evaluation differs")
    if any(check.name == "complete_original_evidence" for check in current.checks):
        return dict(
            status="unknown", business_accepted=False, original_oracle="not_run"
        )
    facts = GroupEvaluationReads(load_group_capture, load_group_inputs)(
        contract, selected, store, control
    )
    projects = facts.before.project_copy == facts.after.project_copy
    original = GROUP(
        json.loads(store.read(facts.spec.native_contract_ref, control)),
        facts.page.model_dump(mode="json"),
        facts.before.state.model_dump(mode="json"),
        facts.after.state.model_dump(mode="json"),
        site_origin=facts.site_origin,
        runtime_error=False,
    )
    original = GUARD(original, runtime_error=False, selected_records_unchanged=projects)
    actual = {
        check.name: check.status
        for check in current.checks
        if check.name != "selected_projects_preserved"
    }
    expected = {
        name: "pass" if value else "fail" for name, value in original["checks"].items()
    }
    flag = not projects
    protection = next(
        check for check in current.checks if check.name == "selected_projects_preserved"
    )
    if (
        (current.status, current.reward, actual)
        != (original["status"], original["reward"], expected)
        or bool(original.get("state_change_requires_review", False)) != flag
        or (protection.status == "fail") != flag
    ):
        raise EvidenceIntegrityError("Original Group goal/project guard differs")
    return dict(
        status=current.status,
        business_accepted=current.status != "unknown",
        original_oracle="all_original_conditions_and_guard_equal",
        state_change_requires_review=flag,
    )
