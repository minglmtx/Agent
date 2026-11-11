"""Selected original capture/context references through the current Evaluator port."""

from typing import Any
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.reddit.evidence_schema import (
    ImageEvidence,
    ImageSiteCapture,
    ImagePageCapture,
)
from lab_generate_skill.evaluators.reddit.native_image import REQUIREMENTS
from lab_generate_skill.bootstrap.reddit_image_evaluation import reddit_image_evaluator
from actor_source_protocol import ActorSource
from test_slurm_commands import guard


def judge_source_task(
    source: ActorSource, facts: dict[str, Any], actor: dict[str, Any]
) -> dict[str, Any]:
    n = source.native

    def pair(label: str) -> ImageSiteCapture:
        capture = facts["catalog_" + label]
        return ImageSiteCapture(
            intent_ref=EvidenceRef.model_validate(capture["intent_ref"]),
            result_ref=EvidenceRef.model_validate(capture["result_ref"]),
        )

    selected = ImageEvidence(
        environment_ref=source.saved["environment_selection_ref"],
        browser_spec_ref=source.saved["browser_spec_ref"],
        before=pair("before"),
        after=pair("after"),
        page=(
            None
            if actor.get("page_capture") is None
            else ImagePageCapture.model_validate(actor["page_capture"])
        ),
        trace_snapshot_ref=(
            None
            if actor.get("trace_snapshot_ref") is None
            else EvidenceRef.model_validate(actor["trace_snapshot_ref"])
        ),
        trace_ref=(
            None
            if actor.get("trace_ref") is None
            else EvidenceRef.model_validate(actor["trace_ref"])
        ),
    )
    contract = EvaluationContract(
        identity=n.public.identity,
        attempt_id=source.saved["baseline_inputs"].prepared.scope.attempt_id,
        task_contract_ref=n.binding_ref,
        public_task_ref=n.binding.public_task_ref,
        completion_spec_ref=n.binding.private_spec_ref,
        requirements=REQUIREMENTS,
        scope="engineering",
    )
    result = reddit_image_evaluator(selected).evaluate(
        contract, source.c.evidence, guard(90)
    )
    return dict(
        selection_ref=n.put(selected).model_dump(mode="json"),
        contract_ref=n.put(contract).model_dump(mode="json"),
        evaluation_ref=n.put(result).model_dump(mode="json"),
        evaluation=result.model_dump(mode="json"),
    )
