"""Fixed selected page collectors, never wire-provided plugin paths."""

from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.ports.browser_capture import BrowserPageCollector


def browser_collector(
    configuration: BrowserWorkerConfiguration,
) -> BrowserPageCollector | None:
    identity = configuration.spec.task.identity
    if (identity.site, identity.family, identity.contract_version, identity.split) == (
        "shopping",
        "page_navigation",
        1,
        "train",
    ):
        from lab_generate_skill.sites.shopping.navigation_page_capture import (
            ShoppingCategoryPageCollector,
        )

        return ShoppingCategoryPageCollector()
    if (identity.site, identity.family, identity.contract_version, identity.split) == (
        "shopping_admin",
        "page_navigation",
        1,
        "train",
    ):
        from lab_generate_skill.sites.shopping_admin.navigation_page_capture import (
            AdminNavigationPageCollector,
        )

        return AdminNavigationPageCollector()
    if (identity.site, identity.contract_version, identity.split) == (
        "gitlab",
        1,
        "train",
    ) and identity.family in ("profile_ssh_key", "group_creation"):
        from lab_generate_skill.sites.gitlab.page_capture import (
            GitlabPageHealthCollector,
        )

        return GitlabPageHealthCollector()
    if (identity.site, identity.family, identity.contract_version, identity.split) == (
        "reddit",
        "native_image_submission",
        1,
        "train",
    ):
        from lab_generate_skill.sites.reddit.page_capture import (
            RedditPageHealthCollector,
        )

        return RedditPageHealthCollector()
    if (identity.site, identity.family, identity.contract_version) == (
        "shopping_admin",
        "product_description",
        1,
    ):
        from lab_generate_skill.sites.shopping_admin.page_capture import (
            AdminPageHealthCollector,
        )

        return AdminPageHealthCollector()
    if (identity.site, identity.family, identity.contract_version) == (
        "shopping",
        "recorded_order_eta",
        1,
    ):
        from lab_generate_skill.sites.shopping.page_capture import (
            ShoppingPageHealthCollector,
        )

        return ShoppingPageHealthCollector()
    return None
