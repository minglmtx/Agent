"""Private Admin instance assembly plan; no site or task admission grant."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_files import SiteFilesPlan
from .database_contract import AdminDatabaseLayout
from lab_generate_skill.domain.admin_navigation_origin import AdminNavigationOrigin


class AdminInstancePlan(Contract):
    schema_version: Literal["admin-instance-plan/1"] = "admin-instance-plan/1"
    files: SiteFilesPlan
    apptainer: str
    navigation_origin: AdminNavigationOrigin | None = None

    @property
    def layout(self) -> AdminDatabaseLayout:
        return AdminDatabaseLayout(
            instance_id=self.files.instance_id,
            node_root=self.files.node_root,
            state_root=self.files.state_root,
            image_path=self.files.image_path,
            image_sha256=self.files.image.sha256,
            apptainer=self.apptainer,
        )

    @model_validator(mode="after")
    def paths(self) -> Self:
        self.layout  # validate all downstream paths before any staging effect
        return self
