"""Explicit installed site choices; configuration cannot name executable code."""

from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.site_worker import WorkerSiteInstance
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_storage import SiteWorkerGuard


def build_site_instance(
    configuration: SiteWorkerConfiguration,
    *,
    worker_guard: SiteWorkerGuard | None = None,
) -> WorkerSiteInstance:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    if configuration.site_id == "map":
        if worker_guard is None:
            raise ValueError(
                "Map requires original live worker guard for complete files"
            )
        from lab_generate_skill.bootstrap.map_instance import build_map_worker

        return build_map_worker(configuration, worker_guard)
    if configuration.site_id == "gitlab":
        if worker_guard is None:
            raise ValueError(
                "GitLab requires original live worker guard for private storage"
            )
        from lab_generate_skill.bootstrap.gitlab_instance import build_gitlab_worker

        return build_gitlab_worker(configuration, worker_guard)
    if configuration.site_id == "reddit":
        if worker_guard is None:
            raise ValueError(
                "Reddit requires original live worker guard for private storage"
            )
        from lab_generate_skill.bootstrap.reddit_instance import build_reddit_worker

        return build_reddit_worker(configuration, worker_guard)
    if configuration.site_id == "shopping_admin":
        from lab_generate_skill.bootstrap.admin_instance import build_admin_instance
        from lab_generate_skill.sites.shopping_admin.instance_contract import (
            AdminInstancePlan,
        )
        from lab_generate_skill.sites.shopping_admin.worker_instance import (
            AdminWorkerInstance,
        )

        return AdminWorkerInstance(
            build_admin_instance(
                AdminInstancePlan(
                    files=configuration.files,
                    apptainer=configuration.apptainer,
                    navigation_origin=(
                        None
                        if configuration.admin_navigation_inputs is None
                        else configuration.admin_navigation_inputs.origin
                    ),
                )
            )
        )
    if configuration.site_id == "shopping":
        from lab_generate_skill.bootstrap.shopping_instance import (
            build_shopping_instance,
            shopping_worker_progress,
        )
        from lab_generate_skill.sites.shopping.worker_instance import (
            ShoppingWorkerInstance,
        )

        if configuration.apptainer != "/usr/bin/apptainer":
            raise ValueError("Shopping fixed native executable differs")

        def customer(control: OperationControl) -> str:
            if configuration.shopping_category_inputs is not None:
                raise ValueError("Category source cannot acquire ETA customer inputs")
            from lab_generate_skill.adapters.browsergym.login_catalog import (
                shopping_login,
            )

            return shopping_login(control)[0]

        return ShoppingWorkerInstance(
            build_shopping_instance(
                configuration.files,
                progress=shopping_worker_progress,
                origin=(
                    None
                    if configuration.shopping_category_inputs is None
                    else configuration.shopping_category_inputs.origin
                ),
            ),
            customer,
        )
    raise ValueError("Unsupported fixed site worker")
