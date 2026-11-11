"""Original Admin v7 declaration from explicit current resource bindings.

This joins data, not permissions. The caller supplies real scope/token/files,
installation and origin; no defaults, allocation, staging, CAS or acquisition.
"""

import hashlib
from lab_generate_skill.domain.admin_navigation_origin import (
    AdminNavigationOrigin,
    AdminNavigationWorkerInputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)


def admin_navigation_configuration(
    private: AdminNavigationSpec,
    scope: StateScope,
    token: AllocationToken,
    files: SiteFilesPlan,
    installation: ReleaseInstallation,
    origin: AdminNavigationOrigin,
) -> SiteWorkerConfiguration:
    private = AdminNavigationSpec.model_validate(private)
    scope = StateScope.model_validate(scope)
    token = AllocationToken.model_validate(token)
    files = SiteFilesPlan.model_validate(files)
    installation = ReleaseInstallation.model_validate(installation)
    origin = AdminNavigationOrigin.model_validate(origin)
    if scope.task != private.task or scope.owner != token.owner:
        raise OwnershipConflict(
            "Admin declaration changed the original task or resource owner"
        )
    payload = NavigationExecutionInput(spec=private).model_dump_json().encode()
    return SiteWorkerConfiguration(
        schema_version="site-worker-configuration/7",
        site_id="shopping_admin",
        token=token,
        files=files,
        apptainer="/usr/bin/apptainer",
        installation=installation,
        private_evidence=None,
        admin_navigation_inputs=AdminNavigationWorkerInputs(
            scope=scope,
            native_contract_sha256=private.native_contract_ref.sha256,
            private_input_sha256=hashlib.sha256(payload).hexdigest(),
            origin=origin,
        ),
    )
