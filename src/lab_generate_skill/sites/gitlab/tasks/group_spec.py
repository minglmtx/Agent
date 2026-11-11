"""Private persisted-group requirements; no execution or training admission."""

from typing import Any, Literal, Self
from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref


class GroupSettings(Contract):
    setup_for_company: bool | None = None
    jobs_to_be_done: Literal[0, 2, 3] | None = None

    @model_serializer(mode="wrap")
    def original_declarations(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        values: dict[str, Any] = handler(self)
        return {
            key: value for key, value in values.items() if key in self.model_fields_set
        }

    @field_validator("jobs_to_be_done", mode="before")
    @classmethod
    def exact_purpose(cls, value: object) -> object:
        if value is not None and type(value) is not int:
            raise ValueError("Native group purpose must be an exact integer")
        return value

    @model_validator(mode="after")
    def declared(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("Persisted group settings require explicit native values")
        # Literal integers alone accept Python booleans; retain the native enum.
        if self.jobs_to_be_done is not None and type(self.jobs_to_be_done) is not int:
            raise ValueError("Native group purpose must be an exact integer")
        return self


class GroupRequirements(Contract):
    name: NonEmptyText | None
    visibility_level: Literal[0, 10, 20] | None
    top_level: bool
    path: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    settings: GroupSettings | None = None

    @model_serializer(mode="wrap")
    def original_declarations(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        values: dict[str, Any] = handler(self)
        for key in ("path", "settings"):
            if key not in self.model_fields_set:
                values.pop(key, None)
        return values

    @field_validator("visibility_level", mode="before")
    @classmethod
    def exact_visibility(cls, value: object) -> object:
        if value is not None and type(value) is not int:
            raise ValueError("Native group visibility must be an exact integer")
        return value

    @model_validator(mode="after")
    def native_types(self) -> Self:
        if self.visibility_level is not None and type(self.visibility_level) is not int:
            raise ValueError("Native group visibility must be an exact integer")
        if any(
            getattr(self, key) is None
            for key in ("path", "settings")
            if key in self.model_fields_set
        ):
            raise ValueError("Optional native group requirements cannot be null")
        return self


class GroupSpec(Contract):
    schema_version: Literal["gitlab-group-creation/1"] = "gitlab-group-creation/1"
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    native_goal: NonEmptyText
    requirements: GroupRequirements
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def selected(self) -> Self:
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("gitlab", "group_creation", 1, "train"):
            raise ValueError("Expected explicit train GitLab group-creation family")
        private_state_ref(self.native_contract_ref, "gitlab-native-contract/1")
        return self
