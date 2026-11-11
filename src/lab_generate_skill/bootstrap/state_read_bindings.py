"""Only compiled pure state semantics; no website or filesystem authority."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.state_qualification import StateQualificationChecks
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_checks import (
    NavigationStateChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_state_checks import GroupStateChecks
from .gitlab_group_capture import load_group_capture


def bind_state_read_checks(
    task: TaskIdentity, evidence: EvidenceStore
) -> StateQualificationChecks:
    task = TaskIdentity.model_validate(task)
    selected = task.site, task.family, task.contract_version, task.split
    if selected == ("shopping_admin", "page_navigation", 1, "train"):
        return NavigationStateChecks(evidence)
    if selected == ("gitlab", "group_creation", 1, "train"):
        return GroupStateChecks(evidence, load_group_capture)
    raise ValueError("No compiled readonly state-check binding for this task")
