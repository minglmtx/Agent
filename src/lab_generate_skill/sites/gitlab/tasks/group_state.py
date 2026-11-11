"""Complete original selected group SQL rows, never a whole-database claim."""

from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.identity import TaskIdentity

NativeId = Annotated[int, Field(ge=1, le=9223372036854775807)]


class GroupAccount(Contract):
    id: NativeId
    username: NonEmptyText


class NativeGroup(Contract):
    id: NativeId
    name: str
    path: str
    type: Literal["Group"]
    visibility_level: int
    parent_id: NativeId | None


class GroupMember(Contract):
    id: NativeId
    source_id: NativeId
    user_id: NativeId
    access_level: int


class NativeGroupSettings(Contract):
    namespace_id: NativeId
    setup_for_company: bool | None
    jobs_to_be_done: int | None


class GroupNativeState(Contract):
    schema_version: Literal["gitlab-group-state/1"] = "gitlab-group-state/1"
    task: TaskIdentity
    user: GroupAccount
    groups: tuple[NativeGroup, ...]
    members: tuple[GroupMember, ...]
    settings: tuple[NativeGroupSettings, ...] | None

    @model_validator(mode="after")
    def identities(self) -> Self:
        for rows in (self.groups, self.members):
            if len({row.id for row in rows}) != len(rows):
                raise ValueError("Duplicate native group or member identity")
        if self.settings is not None and len(
            {row.namespace_id for row in self.settings}
        ) != len(self.settings):
            raise ValueError("Duplicate native group settings identity")
        return self
