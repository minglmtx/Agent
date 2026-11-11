"""Selected original Admin page navigation data, without admission or effects."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.validation import Contract, NonEmptyText


class AdminNavigationSpec(Contract):
    schema_version: Literal["shopping-admin-page-navigation/1"] = (
        "shopping-admin-page-navigation/1"
    )
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    legacy_runtime_task_id: NonEmptyText
    store_id: int = Field(ge=0, le=0)
    start_path: NonEmptyText
    target_path: NonEmptyText
    heading: NonEmptyText = Field(max_length=4096)
    label: NonEmptyText = Field(max_length=4096)
    initialization: Literal[
        "fixed_local_start_not_original_trajectory_start",
        "declared_local_start; original goal unchanged",
    ]
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def original_family(self) -> Self:
        if (self.task.site, self.task.family, self.task.contract_version) != (
            "shopping_admin",
            "page_navigation",
            1,
        ):
            raise ValueError("Explicit current Admin page_navigation family required")
        if (
            self.native_contract_ref.content_schema,
            self.native_contract_ref.visibility,
            self.native_contract_ref.media_type,
        ) != ("admin-native-contract/1", "private", "application/json"):
            raise ValueError("Private original Admin native JSON required")
        prefix = self.task.source_task_id + "@derived-"
        if (
            not self.legacy_runtime_task_id.startswith(prefix)
            or self.legacy_runtime_task_id == prefix
        ):
            raise ValueError("Original derived runtime lineage required")
        for path in (self.start_path, self.target_path):
            if (
                not path.startswith("/")
                or path.startswith("//")
                or any(c in path for c in ("?", "#", "\\"))
                or any(c.isspace() for c in path)
                or any(p in (".", "..") for p in path.split("/"))
            ):
                raise ValueError("Original local Admin route required")
        return self


class AdminNavigationInputs(Contract):
    schema_version: Literal["shopping-admin-page-navigation-inputs/1"] = (
        "shopping-admin-page-navigation-inputs/1"
    )
    public_task: PublicTask
    private_spec: AdminNavigationSpec

    @model_validator(mode="after")
    def same_original_task(self) -> Self:
        if self.public_task.identity != self.private_spec.task:
            raise ValueError("Public/private navigation task identities differ")
        return self
