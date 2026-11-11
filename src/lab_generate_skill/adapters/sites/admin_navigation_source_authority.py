"""Original Admin navigation source declaration, with no Actor/task dispatch right."""

from lab_generate_skill.domain.admin_navigation_origin import (
    AdminNavigationWorkerInputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from .source_site_lifecycle import SourceSiteLifecycleAuthority


class AdminNavigationSourceSiteAuthority(SourceSiteLifecycleAuthority):
    def verify_source_declaration(self) -> None:
        cfg = self.spec.configuration
        inputs = cfg.admin_navigation_inputs
        if (
            cfg.site_id != "shopping_admin"
            or cfg.schema_version != "site-worker-configuration/7"
            or not isinstance(inputs, AdminNavigationWorkerInputs)
            or inputs.scope != self.owner.scope
        ):
            raise OwnershipConflict(
                "Original version7 Admin navigation source scope required"
            )
