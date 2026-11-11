"""Fixed initialization dispatch only; no dynamic imports from wire identifiers."""

from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_initialization import (
    AdminProductInitialization,
    ShoppingOrderInitialization,
)
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
    GitlabGroupInitialization,
)
from lab_generate_skill.ports.browser_initialization import BrowserInitializer
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.ports.lifecycle import Clock
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink


from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)


def browser_initializer(
    config: BrowserWorkerConfiguration,
    *,
    clock: Clock | None = None,
    map_evidence: MapArtifactSink | None = None,
) -> BrowserInitializer:
    config = BrowserWorkerConfiguration.model_validate(config)
    if isinstance(config.initialization, MapNavigationInitialization):
        if clock is None:
            raise ValueError("Navigation initialization requires original clock")
        from lab_generate_skill.sites.map.navigation_browser_initialization import (
            MapNavigationBrowserInitializer,
        )

        return MapNavigationBrowserInitializer(config.initialization, clock)
    if isinstance(config.initialization, MapNativeInitialization):
        if clock is None or map_evidence is None:
            raise ValueError(
                "Map initialization requires original clock and full-file evidence sink"
            )
        from lab_generate_skill.sites.map.browser_initialization import (
            MapNativeBrowserInitializer,
        )

        return MapNativeBrowserInitializer(config.initialization, clock, map_evidence)
    if isinstance(config.initialization, RedditNativeImageInitialization):
        from lab_generate_skill.sites.reddit.browser_initialization import (
            RedditNativeImageBrowserInitializer,
        )
        from lab_generate_skill.adapters.browsergym.login_catalog import reddit_login

        return RedditNativeImageBrowserInitializer(config.initialization, reddit_login)
    if isinstance(config.initialization, GitlabGroupInitialization):
        from lab_generate_skill.sites.gitlab.browser_initialization import (
            GitlabGroupBrowserInitializer,
        )
        from lab_generate_skill.adapters.browsergym.login_catalog import gitlab_login

        return GitlabGroupBrowserInitializer(config.initialization, gitlab_login)
    if isinstance(config.initialization, GitlabSshKeyInitialization):
        from lab_generate_skill.sites.gitlab.browser_initialization import (
            GitlabSshKeyBrowserInitializer,
        )
        from lab_generate_skill.adapters.browsergym.login_catalog import gitlab_login

        return GitlabSshKeyBrowserInitializer(config.initialization, gitlab_login)
    if isinstance(config.initialization, AdminNavigationInitialization):
        from lab_generate_skill.sites.shopping_admin.navigation_browser_initialization import (
            AdminNavigationBrowserInitializer,
        )
        from lab_generate_skill.adapters.browsergym.login_catalog import admin_login

        return AdminNavigationBrowserInitializer(config.initialization, admin_login)
    if isinstance(config.initialization, AdminProductInitialization):
        from lab_generate_skill.sites.shopping_admin.browser_initialization import (
            AdminProductBrowserInitializer,
        )
        from lab_generate_skill.adapters.browsergym.login_catalog import admin_login

        return AdminProductBrowserInitializer(config.initialization, admin_login)
    if isinstance(config.initialization, ShoppingCategoryInitialization):
        from lab_generate_skill.sites.shopping.navigation_browser_initialization import (
            ShoppingCategoryBrowserInitializer,
        )

        return ShoppingCategoryBrowserInitializer(config.initialization)
    if isinstance(config.initialization, ShoppingOrderInitialization):
        from lab_generate_skill.sites.shopping.browser_initialization import (
            ShoppingOrderBrowserInitializer,
        )
        from lab_generate_skill.adapters.browsergym.login_catalog import shopping_login

        return ShoppingOrderBrowserInitializer(config.initialization, shopping_login)
    from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask

    return NavigatePublicTask()
