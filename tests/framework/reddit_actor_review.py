"""Readonly original capsule guard/goals and full restored baseline recomputation."""

from typing import Any
import json
from lab_generate_skill.bootstrap.reddit_image_evaluation import reddit_image_evaluator
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.bootstrap.reddit_issued_ax import last_issued_ax
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.reset import ResetInputs
from lab_generate_skill.domain.state_qualification import ResetSelection
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.evaluation_reads import ImageEvaluationReads
from lab_generate_skill.sites.reddit.evidence_schema import ImageEvidence
from lab_generate_skill.sites.reddit.tasks.image_state_checks import ImageStateChecks
from reddit_original_image_oracle import oracle, goal_oracle


def review_reddit_judgment(
    contract: EvaluationContract,
    selected: ImageEvidence,
    saved: Evaluation,
    store: EvidenceReader,
    control: OperationControl,
) -> dict[str, Any]:
    current = reddit_image_evaluator(selected).evaluate(contract, store, control)
    if current != saved:
        raise EvidenceIntegrityError("Independent Reddit evaluation differs")
    if saved.status == "unknown":
        return dict(
            status="unknown", business_accepted=False, original_oracle="not_run"
        )
    facts = ImageEvaluationReads(load_image_inputs, last_issued_ax)(
        contract, selected, store, control
    )
    control.checkpoint()
    initial = facts.reference.model_dump(mode="json")
    after = facts.after.model_dump(mode="json")
    integrity = oracle()(initial, after)
    original = goal_oracle(facts.spec.native_contract_ref)(
        json.loads(store.read(facts.spec.native_contract_ref, control)),
        initial,
        after,
        facts.page.model_dump(mode="json"),
        [{"actual_issued_ax": facts.last_issued_ax}],
        site_origin=facts.public.start_url,
        integrity=integrity,
    )
    actual = {check.name: check.status for check in saved.checks}
    expected = {
        name: "pass" if passed else "fail"
        for name, passed in original["checks"].items()
    }
    if integrity is not True or (saved.status, saved.reward, actual) != (
        original["status"],
        original["reward"],
        expected,
    ):
        raise EvidenceIntegrityError(
            "Original Reddit conditional goal or full protection differs"
        )
    control.checkpoint()
    return dict(
        status=saved.status,
        business_accepted=True,
        original_oracle="conditional_checks_equal",
        checked_names=list(expected),
        full_original_mutation_scope=True,
    )


def review_reddit_reset(
    site: dict[str, Any],
    inputs: ResetInputs,
    store: EvidenceReader,
    control: OperationControl,
) -> None:
    ref = EvidenceRef.model_validate(site["qualified_source"]["reset_selection_ref"])
    checks = ImageStateChecks(store)
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
        raise EvidenceIntegrityError("Independent Reddit full reset differs")
