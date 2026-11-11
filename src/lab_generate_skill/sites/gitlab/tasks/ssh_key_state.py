"""Complete private SSH-key facts; no database commands or execution rights."""

import json
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from pydantic import (
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.identity import TaskIdentity

Column = Annotated[str, StringConstraints(pattern=r"\A[A-Za-z_][A-Za-z0-9_]*\z")]
Oid = Annotated[str, StringConstraints(pattern=r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\z")]
AUTH_COLUMNS = (
    "sign_in_count",
    "current_sign_in_at",
    "last_sign_in_at",
    "current_sign_in_ip",
    "last_sign_in_ip",
    "remember_created_at",
    "last_activity_on",
    "updated_at",
)
PROTECTED_TABLES = (
    "projects",
    "namespaces",
    "routes",
    "issues",
    "merge_requests",
    "users",
    "issue_assignees",
    "merge_request_assignees",
    "milestones",
    "labels",
    "label_links",
    "timelogs",
    "approvals",
    "merge_request_metrics",
    "project_authorizations",
    "members",
)


def original_true(value: object) -> object:
    if value is not True:
        raise ValueError("Explicit complete original capture required")
    return value


class NativeTable(Contract):
    table: Literal["users", "keys"]
    columns: tuple[Column, ...] = Field(min_length=1)
    rows: tuple[dict[str, JsonValue], ...]
    row_count: int = Field(ge=0)
    complete: Literal[True]

    _complete = field_validator("complete", mode="before")(original_true)

    @model_validator(mode="after")
    def complete_rows(self) -> Self:
        columns = set(self.columns)
        required = (
            {"id", "username", "admin", "external", "state", *AUTH_COLUMNS}
            if self.table == "users"
            else {"id", "user_id", "key", "title"}
        )
        if (
            not required <= columns
            or len(columns) != len(self.columns)
            or self.row_count != len(self.rows)
        ):
            raise ValueError("Full ordered native table/schema/row count required")
        cursor = 0
        for row in self.rows:
            ident = row.get("id")
            if set(row) != columns or type(ident) is not int or ident <= cursor:
                raise ValueError(
                    "Complete strictly ordered unique native rows required"
                )
            cursor = ident
            if self.table == "users" and (
                type(row["admin"]) is not bool
                or type(row["external"]) is not bool
                or not isinstance(row["username"], str)
                or not row["username"]
                or not isinstance(row["state"], str)
            ):
                raise ValueError("Native users identity and flags changed SQL types")
            if self.table == "keys" and (
                (row["user_id"] is not None and type(row["user_id"]) is not int)
                or not isinstance(row["key"], str)
                or (row["title"] is not None and not isinstance(row["title"], str))
                or any(
                    row.get(name) is not None and not isinstance(row.get(name), str)
                    for name in ("fingerprint", "fingerprint_sha256")
                )
            ):
                raise ValueError(
                    "Native key identity/material/fingerprint types invalid"
                )
        json.dumps(self.rows, allow_nan=False)
        return self


class NativeGuardTable(Contract):
    rows: int = Field(ge=0)
    columns: tuple[Column, ...] = Field(min_length=1)
    key: tuple[Column, ...] = Field(min_length=1)
    sha256: Sha256

    @model_validator(mode="after")
    def native_schema(self) -> Self:
        if (
            len(set(self.columns)) != len(self.columns)
            or len(set(self.key)) != len(self.key)
            or not set(self.key) <= set(self.columns)
        ):
            raise ValueError("Complete native protected schema and unique key required")
        return self


class NativeRepository(Contract):
    head: Oid | None
    symbolic_head: str | None
    refs: dict[str, Oid]

    @model_validator(mode="after")
    def original_refs(self) -> Self:
        names = list(self.refs)
        if self.symbolic_head is not None:
            if not self.symbolic_head.startswith("refs/heads/"):
                raise ValueError("Native symbolic HEAD is not a branch reference")
            names.append(self.symbolic_head)
        for name in names:
            if (
                not name.startswith("refs/")
                or any(ord(c) <= 32 for c in name)
                or ".." in name
                or str(PurePosixPath(name)) != name
                or any(c in name for c in ("~", "^", ":", "?", "*", "[", "\\"))
                or "@{" in name
                or any(
                    part.startswith(".") or part.endswith((".", ".lock"))
                    for part in name.split("/")
                )
            ):
                raise ValueError("Original native Git reference name required")
        return self


class NativeRepositories(Contract):
    version: Literal["gitlab-all-native-refs-v1"]
    complete: Literal[True]
    repositories: dict[str, NativeRepository] = Field(min_length=1)

    _complete = field_validator("complete", mode="before")(original_true)

    @model_validator(mode="after")
    def all_original_repositories(self) -> Self:
        for path in self.repositories:
            parsed = PurePosixPath(path)
            if (
                not path.endswith(".git")
                or parsed.is_absolute()
                or ".." in parsed.parts
                or str(parsed) != path
                or any(ord(c) < 32 for c in path)
            ):
                raise ValueError(
                    "Complete original relative repository discovery required"
                )
        return self


class NativeAccount(Contract):
    id: int = Field(ge=1)
    username: str = Field(pattern=r"\A[A-Za-z0-9_.-]+\z")
    admin: Literal[False]
    external: bool
    state: Literal["active"]

    @field_validator("admin", mode="before")
    @classmethod
    def ordinary_account(cls, value: object) -> object:
        if value is not False:
            raise ValueError("Original ordinary account required")
        return value


class SshKeyNativeState(Contract):
    schema_version: Literal["gitlab-ssh-key-state/1"] = "gitlab-ssh-key-state/1"
    task: TaskIdentity
    account: NativeAccount
    users: NativeTable
    keys: NativeTable
    guard: dict[str, NativeGuardTable]
    refs: NativeRepositories

    @model_validator(mode="after")
    def complete_original_state(self) -> Self:
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("gitlab", "profile_ssh_key", 1, "train"):
            raise ValueError("Selected derived GitLab SSH-key train facts required")
        if (
            self.users.table != "users"
            or self.keys.table != "keys"
            or set(self.guard) != set(PROTECTED_TABLES)
        ):
            raise ValueError(
                "Full users/keys and all sixteen original protected tables required"
            )
        user_guard = self.guard["users"]
        if (user_guard.rows, user_guard.columns) != (
            self.users.row_count,
            self.users.columns,
        ):
            raise ValueError(
                "Native users table differs from complete guard schema/count"
            )
        matches = [row for row in self.users.rows if row["id"] == self.account.id]
        if len(matches) != 1 or any(
            matches[0][name] != value
            for name, value in self.account.model_dump().items()
        ):
            raise ValueError(
                "Full native users table does not identify original ordinary account"
            )
        return self
