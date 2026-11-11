"""Pure Group browser declaration, after the original native/public binding."""

from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)


def group_browser_declaration(
    public: PublicTask,
    endpoint: str,
    native_account_id: int,
    prepared_ref: EvidenceRef,
    site_ref: EvidenceRef,
) -> GitlabGroupInitialization:
    """Bind an explicit original start; account/permission qualification stays live."""
    public = PublicTask.model_validate(public)
    selected = GitlabGroupInitialization(
        endpoint=endpoint,
        native_account_id=native_account_id,
        prepared_ref=prepared_ref,
        site_ref=site_ref,
    )
    if public.start_url != endpoint + "groups/new":
        original = urlsplit(public.start_url)
        start = original.path + ("#" + original.fragment if original.fragment else "")
        selected = GitlabGroupInitialization.model_validate(
            {**selected.model_dump(), "start_path": start}
        )
    selected.check_task(public)
    return selected
