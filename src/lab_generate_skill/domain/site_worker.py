"""Frozen site-worker inputs and observed endpoint; no execution permission."""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from pydantic import (
    Field,
    field_validator,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .validation import Contract
from .site_files import SiteFilesPlan
from .lifecycle import AllocationToken, OperationContext
from .release_installation import ReleaseInstallation, InstalledReleaseSources
from .process_guard import ProcessOwnerGuard
from .errors import OwnershipConflict
from .site_evidence import SitePrivateEvidencePlan
from .map_worker_inputs import MapWorkerInputs
from .map_navigation_worker_inputs import MapNavigationWorkerInputs
from .admin_navigation_origin import AdminNavigationWorkerInputs
from .gitlab_group_origin import GitlabGroupWorkerInputs
from .shopping_navigation_origin import ShoppingCategoryWorkerInputs
from .native_private_json import GITLAB_GROUP_PRIVATE_JSON

MapSiteWorkerInputs = Annotated[
    MapWorkerInputs | MapNavigationWorkerInputs, Field(discriminator="schema_version")
]


class SiteWorkerConfiguration(Contract):
    schema_version: Literal[
        "site-worker-configuration/6",
        "site-worker-configuration/7",
        "site-worker-configuration/8",
        "site-worker-configuration/9",
    ] = "site-worker-configuration/6"
    site_id: Literal["shopping_admin", "shopping", "gitlab", "reddit", "map"]
    token: AllocationToken
    files: SiteFilesPlan
    apptainer: str
    installation: ReleaseInstallation
    private_evidence: SitePrivateEvidencePlan | None
    map_inputs: MapSiteWorkerInputs | None = None
    admin_navigation_inputs: AdminNavigationWorkerInputs | None = None
    gitlab_group_inputs: GitlabGroupWorkerInputs | None = None
    shopping_category_inputs: ShoppingCategoryWorkerInputs | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.schema_version != "site-worker-configuration/7":
            value.pop("admin_navigation_inputs", None)
        if self.schema_version != "site-worker-configuration/8":
            value.pop("gitlab_group_inputs", None)
        if self.schema_version != "site-worker-configuration/9":
            value.pop("shopping_category_inputs", None)
        return value

    @field_validator("apptainer")
    @classmethod
    def executable(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def original_instance(self) -> Self:
        token = self.token
        navigation = self.admin_navigation_inputs
        group = self.gitlab_group_inputs
        category = self.shopping_category_inputs
        if self.schema_version == "site-worker-configuration/9":
            if (
                self.site_id != "shopping"
                or category is None
                or category.scope.owner != token.owner
                or self.apptainer != "/usr/bin/apptainer"
            ):
                raise ValueError("Version9 requires original category owner/inputs")
        elif category is not None:
            raise ValueError("Explicit category inputs require configuration version9")
        if self.schema_version == "site-worker-configuration/8":
            if (
                self.site_id != "gitlab"
                or group is None
                or group.scope.owner != token.owner
                or self.private_evidence is None
                or self.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            ):
                raise ValueError(
                    "Version8 requires the original Group owner/profile/inputs"
                )
        elif group is not None:
            raise ValueError("Explicit Group inputs require configuration version8")
        if self.schema_version == "site-worker-configuration/7":
            if (
                self.site_id != "shopping_admin"
                or navigation is None
                or navigation.scope.owner != token.owner
                or self.apptainer != "/usr/bin/apptainer"
            ):
                raise ValueError(
                    "Version7 requires the original Admin navigation owner/inputs"
                )
        elif navigation is not None:
            raise ValueError(
                "Explicit Admin navigation requires configuration version7"
            )
        if (
            self.site_id in ("shopping", "gitlab", "reddit", "map")
            and self.apptainer != "/usr/bin/apptainer"
        ):
            raise ValueError("Selected site requires its fixed native executable")
        if (
            token.scope,
            token.resource_kind,
            token.provider_id,
            token.provider_version,
        ) != ("batch", "site", "fixed-site-worker", "6"):
            raise ValueError("Site worker requires its original batch site allocation")
        if token.expected_resource_id != self.files.instance_id:
            raise ValueError("Site files changed original allocated instance")
        if self.site_id == "map":
            if (
                self.map_inputs is None
                or self.map_inputs.runtime.files != self.files
                or self.map_inputs.scope.owner != token.owner
            ):
                raise ValueError(
                    "Map requires exact original runtime files and source owner"
                )
        elif self.map_inputs is not None:
            raise ValueError("Map runtime inputs are not another site's configuration")
        if self.site_id in ("gitlab", "reddit"):
            if self.private_evidence is None:
                raise ValueError(
                    "Selected native site requires predeclared complete private evidence storage"
                )
            self.private_evidence.check_site(token, self.files, self.installation)
            if self.private_evidence.profile.site_id != self.site_id:
                raise ValueError("Private native profile changed original site")
        elif self.private_evidence is not None:
            raise ValueError(
                "Private native storage is declared only for selected native consumers"
            )
        return self

    def check_operation(self, operation: OperationContext, mode: str) -> None:
        token = self.token
        if operation.mode != mode or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
        ) != (
            token.owner.run_id,
            token.owner.owner_id,
            token.attempt_id,
            token.allocation_id,
            token.recovery_ref,
        ):
            raise OwnershipConflict(
                "Site operation changed original allocation/recovery"
            )


class SiteInstanceStarted(Contract):
    schema_version: Literal["site-instance-started/1"] = "site-instance-started/1"
    files: SiteFilesPlan
    endpoint: str = Field(min_length=1, max_length=4096)
    ports: tuple[int, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def addresses(self) -> Self:
        if any(not 1024 <= p <= 65535 for p in self.ports) or len(
            set(self.ports)
        ) != len(self.ports):
            raise ValueError("Expected distinct unprivileged service ports")
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != self.ports[0]
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(ord(c) < 33 for c in self.endpoint)
        ):
            raise ValueError("Site endpoint must use its first original loopback port")
        return self


class SiteWorkerReady(Contract):
    """Verified original worker before instance creation; not site acquisition."""

    schema_version: Literal["site-worker-ready/1"] = "site-worker-ready/1"
    owner_guard: ProcessOwnerGuard
    installed_sources: InstalledReleaseSources
