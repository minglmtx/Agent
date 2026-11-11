"""Declare the existing category worker from exact task and resource inputs.

Pure composition only. The original worker still owns image verification,
exclusive ports, acquisition, initial measurements and complete restoration.
"""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.shopping_navigation_origin import (
    ShoppingCategoryOrigin,
    ShoppingCategoryWorkerInputs,
)
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA


def shopping_category_site_configuration(
    private: CategoryNavigationSpec,
    scope: StateScope,
    token: AllocationToken,
    files: SiteFilesPlan,
    installation: ReleaseInstallation,
    origin: ShoppingCategoryOrigin,
) -> SiteWorkerConfiguration:
    if not all(
        isinstance(value, expected)
        for value, expected in (
            (private, CategoryNavigationSpec),
            (scope, StateScope),
            (token, AllocationToken),
            (files, SiteFilesPlan),
            (installation, ReleaseInstallation),
            (origin, ShoppingCategoryOrigin),
        )
    ):
        raise TypeError("Typed original category task/resource declarations required")
    private = CategoryNavigationSpec.model_validate(private)
    scope = StateScope.model_validate(scope)
    token = AllocationToken.model_validate(token)
    files = SiteFilesPlan.model_validate(files)
    installation = ReleaseInstallation.model_validate(installation)
    origin = ShoppingCategoryOrigin.model_validate(origin)
    if (
        scope.task != private.task
        or scope.owner != token.owner
        or files.image.sha256 != SHOPPING_IMAGE_SHA
        or files.workspace_root != installation.workspace_root
    ):
        raise OwnershipConflict(
            "Category declaration changed original task/owner/image/workspace"
        )
    payload = CategoryNavigationExecutionInput(spec=private).model_dump_json().encode()
    return SiteWorkerConfiguration(
        schema_version="site-worker-configuration/9",
        site_id="shopping",
        token=token,
        files=files,
        installation=installation,
        apptainer="/usr/bin/apptainer",
        private_evidence=None,
        shopping_category_inputs=ShoppingCategoryWorkerInputs(
            scope=scope,
            native_contract_sha256=private.native_contract_ref.sha256,
            private_input_sha256=hashlib.sha256(payload).hexdigest(),
            origin=origin,
        ),
    )
