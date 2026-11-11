"""Original selected Group/SSH evidence through one current Evaluator port."""

from typing import Any
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.gitlab.evidence_schema import (
    SshKeyEvidence,
    GroupEvidence,
    GitlabSiteCapture,
    GitlabPageCapture,
)
from lab_generate_skill.evaluators.gitlab.ssh_key import REQUIREMENTS
from lab_generate_skill.evaluators.gitlab.group import (
    REQUIREMENTS as GROUP_REQUIREMENTS,
)
from lab_generate_skill.bootstrap.gitlab_ssh_evaluation import gitlab_ssh_evaluator
from lab_generate_skill.bootstrap.gitlab_group_evaluation import gitlab_group_evaluator
from actor_source_protocol import ActorSource
from gitlab_source_selection import check_gitlab_task
from test_slurm_commands import guard


def judge_source_task(
    source: ActorSource, facts: dict[str, Any], actor: dict[str, Any]
) -> dict[str, Any]:
    n = source.native
    group = check_gitlab_task(source.c.spec.configuration, n.public.identity)

    def pair(label: str) -> GitlabSiteCapture:
        capture = facts["catalog_" + label]
        return GitlabSiteCapture(
            intent_ref=EvidenceRef.model_validate(capture["intent_ref"]),
            result_ref=EvidenceRef.model_validate(capture["result_ref"]),
        )

    selected_type = GroupEvidence if group else SshKeyEvidence
    selected = selected_type(
        environment_ref=source.saved["environment_selection_ref"],
        browser_spec_ref=source.saved["browser_spec_ref"],
        before=pair("before"),
        after=pair("after"),
        page=(
            None
            if actor.get("page_capture") is None
            else GitlabPageCapture.model_validate(actor["page_capture"])
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
        requirements=GROUP_REQUIREMENTS if group else REQUIREMENTS,
        scope="engineering",
    )
    evaluator = (
        gitlab_group_evaluator(selected)
        if isinstance(selected, GroupEvidence)
        else gitlab_ssh_evaluator(selected)
    )
    result = evaluator.evaluate(contract, source.c.evidence, guard(90))
    return dict(
        selection_ref=n.put(selected).model_dump(mode="json"),
        contract_ref=n.put(contract).model_dump(mode="json"),
        evaluation_ref=n.put(result).model_dump(mode="json"),
        evaluation=result.model_dump(mode="json"),
    )
