"""Original Group source-only declaration on the existing site lifecycle authority."""

from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from lab_generate_skill.adapters.sites.source_site_lifecycle import (
    SourceSiteLifecycleAuthority,
)


class GroupSourceSiteAuthority(SourceSiteLifecycleAuthority):
    def verify_source_declaration(self) -> None:
        cfg, task = self.spec.configuration, self.owner.scope.task
        if (
            cfg.site_id != "gitlab"
            or (task.site, task.family, task.contract_version, task.split)
            != ("gitlab", "group_creation", 1, "train")
            or cfg.private_evidence is None
            or cfg.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            or cfg.files.image.sha256 != GITLAB_IMAGE_SHA
        ):
            raise OwnershipConflict(
                "Original Group source native profile/image/task required"
            )
