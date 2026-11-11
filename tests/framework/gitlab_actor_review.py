"""Readonly selected native oracle and full restoration recomputation."""

from typing import Any
import json
from lab_generate_skill.bootstrap.gitlab_ssh_evaluation import gitlab_ssh_evaluator
from lab_generate_skill.bootstrap.gitlab_ssh_key import load_ssh_key_inputs
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.reset import ResetInputs
from lab_generate_skill.domain.state_qualification import ResetSelection
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.evaluation_reads import SshKeyEvaluationReads
from lab_generate_skill.sites.gitlab.evidence_schema import (
    SshKeyEvidence,
    GroupEvidence,
    CHECKS,
)
from lab_generate_skill.sites.gitlab.tasks.group_state_checks import GroupStateChecks
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from gitlab_source_selection import group_task
from gitlab_group_actor_review import review_group_judgment
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state_checks import SshKeyStateChecks
from test_gitlab_ssh_rule_reference import reference_oracle, legacy_state


def review_gitlab_judgment(
    contract: EvaluationContract,
    selected: SshKeyEvidence | GroupEvidence,
    saved: Evaluation,
    store: EvidenceReader,
    control: OperationControl,
) -> dict[str, Any]:
    if isinstance(selected, GroupEvidence):
        return review_group_judgment(contract, selected, saved, store, control)
    current = gitlab_ssh_evaluator(selected).evaluate(contract, store, control)
    if current != saved:
        raise EvidenceIntegrityError("Independent GitLab evaluation differs")
    # Missing evidence remains unknown. It cannot be promoted by a legacy
    # oracle that lacks the new complete-evidence admission checks.
    if saved.status == "unknown":
        return dict(
            status="unknown", business_accepted=False, original_oracle="not_run"
        )
    facts = SshKeyEvaluationReads(load_ssh_key_state, load_ssh_key_inputs)(
        contract, selected, store, control
    )
    original = reference_oracle(
        json.loads(store.read(facts.spec.native_contract_ref, control)),
        legacy_state(facts.before),
        legacy_state(facts.after),
        [],
        facts.page.model_dump(mode="json"),
        site_origin=facts.public.start_url,
    )
    actual = tuple(check.status for check in saved.checks)
    expected = tuple("pass" if original["checks"][name] else "fail" for name in CHECKS)
    if (saved.status, saved.reward, actual) != (
        original["status"],
        original["reward"],
        expected,
    ):
        raise EvidenceIntegrityError("Original GitLab seven-condition oracle differs")
    return dict(
        status=saved.status, original_oracle="all_seven_equal", business_accepted=True
    )


def review_gitlab_reset(
    site: dict[str, Any],
    inputs: ResetInputs,
    store: EvidenceReader,
    control: OperationControl,
) -> None:
    ref = EvidenceRef.model_validate(site["qualified_source"]["reset_selection_ref"])
    checks = (
        GroupStateChecks(store, load_group_capture)
        if group_task(inputs.spec.task)
        else SshKeyStateChecks(store, load_ssh_key_state)
    )
    selection = checks.read(ref, "reset-selection/1", ResetSelection, control)
    expected = checks.reset(selection, ref, control)
    if (
        expected.plan,
        expected.task,
        expected.environment,
        expected.health,
        expected.closures,
    ) != (
        inputs.plan,
        inputs.task.checks,
        inputs.environment.checks,
        inputs.health.checks,
        inputs.closures,
    ):
        raise EvidenceIntegrityError("Independent GitLab full reset differs")
