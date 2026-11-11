"""Assemble the existing Evaluator port with selected readonly site semantics."""

from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.sites.gitlab.evidence_schema import SshKeyEvidence
from lab_generate_skill.sites.gitlab.evaluation_reads import SshKeyEvaluationReads
from lab_generate_skill.sites.gitlab.tasks.ssh_key_rules import decide_ssh_key
from lab_generate_skill.evaluators.gitlab.ssh_key import SshKeyEvaluator
from .gitlab_ssh_state import load_ssh_key_state
from .gitlab_ssh_key import load_ssh_key_inputs


def gitlab_ssh_evaluator(selected: SshKeyEvidence) -> Evaluator:
    return SshKeyEvaluator(
        selected,
        SshKeyEvaluationReads(load_ssh_key_state, load_ssh_key_inputs),
        decide_ssh_key,
    )
