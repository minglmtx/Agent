"""Category source site scope; native intent and live rights remain mandatory."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from .source_site_lifecycle import SourceSiteLifecycleAuthority


class CategoryNavigationSourceSiteAuthority(SourceSiteLifecycleAuthority):
    def verify_source_declaration(self) -> None:
        cfg = self.spec.configuration
        inputs = cfg.shopping_category_inputs
        if (
            cfg.site_id != "shopping"
            or cfg.schema_version != "site-worker-configuration/9"
            or inputs is None
            or inputs.scope != self.owner.scope
            or cfg.files.image.sha256 != SHOPPING_IMAGE_SHA
        ):
            raise OwnershipConflict(
                "Original category source configuration/image required"
            )
        category_navigation_initial_spec(self.owner.scope.task)
