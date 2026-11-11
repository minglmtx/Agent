"""Bind original Group semantics to the existing readonly Evaluator port."""

from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.sites.gitlab.evidence_schema import GroupEvidence
from lab_generate_skill.sites.gitlab.group_evaluation_reads import GroupEvaluationReads
from lab_generate_skill.sites.gitlab.tasks.group_rules import decide_group
from lab_generate_skill.evaluators.gitlab.group import GroupEvaluator
from .gitlab_group_capture import load_group_capture
from .gitlab_group import load_group_inputs


def gitlab_group_evaluator(selected: GroupEvidence) -> Evaluator:
    return GroupEvaluator(
        selected,
        GroupEvaluationReads(load_group_capture, load_group_inputs),
        decide_group,
    )
