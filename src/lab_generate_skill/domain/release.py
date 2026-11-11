"""Closed frozen release graph; content identity is separate from compatibility.

No current pointer, filesystem discovery, permission or runtime import here.
A valid graph binds all roles but does not prove their implementations work.
"""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Identifier, Sha256

ReleaseKind = Literal[
    "task_adapter",
    "collector",
    "evidence_schema",
    "recovery",
    "code",
    "python",
    "model",
    "browser",
    "site",
    "registry",
    "actor_protocol",
    "teacher_processor",
    "evaluator",
    "reviewer",
    "method",
]
ReleaseRoleName = Literal[
    "code",
    "python",
    "registry",
    "actor",
    "generator",
    "teacher",
    "encoder",
    "actor_protocol",
    "teacher_processor",
    "method",
    "browser",
    "site",
    "evaluator",
    "reviewer",
]
GLOBAL_ROLES = frozenset(
    {
        "code",
        "python",
        "registry",
        "actor",
        "generator",
        "teacher",
        "encoder",
        "actor_protocol",
        "teacher_processor",
        "method",
    }
)
SITE_ROLES = frozenset({"browser", "site", "evaluator", "reviewer"})
ROLE_KIND = {
    name: ("model" if name in {"actor", "generator", "teacher", "encoder"} else name)
    for name in GLOBAL_ROLES | SITE_ROLES
}


class ReleaseFile(Contract):
    path: str = Field(min_length=1, max_length=4096)
    sha256: Sha256
    size_bytes: int = Field(ge=0, le=2 * 1024**4)
    executable: bool

    @field_validator("path")
    @classmethod
    def relative_file(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or str(path) != value
            or value == "."
            or ".." in path.parts
            or "\0" in value
            or "\\" in value
        ):
            raise ValueError("Release file must be a canonical relative POSIX path")
        return value


class ReleaseArtifact(Contract):
    artifact_id: Identifier
    root: str = Field(min_length=1, max_length=4096)
    files: tuple[ReleaseFile, ...] = Field(min_length=1, max_length=100000)

    @field_validator("root")
    @classmethod
    def absolute_root(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not path.is_absolute()
            or str(path) != value
            or ".." in path.parts
            or "\0" in value
            or "\\" in value
        ):
            raise ValueError("Artifact root must be a canonical absolute POSIX path")
        return value

    @model_validator(mode="after")
    def file_set(self) -> Self:
        paths = {file.path for file in self.files}
        if len(paths) != len(self.files):
            raise ValueError("Duplicate release file")
        for name in paths:
            if any(
                str(parent) in paths
                for parent in PurePosixPath(name).parents
                if str(parent) != "."
            ):
                raise ValueError("A release file cannot also be a directory")
        return self


class ReleaseComponent(Contract):
    component_id: Identifier
    kind: ReleaseKind
    interface_id: Identifier
    contract_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+$")
    artifact_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    dependencies: tuple[Identifier, ...] = Field(max_length=512)

    @model_validator(mode="after")
    def unique_references(self) -> Self:
        if len(set(self.artifact_ids)) != len(self.artifact_ids) or len(
            set(self.dependencies)
        ) != len(self.dependencies):
            raise ValueError("Duplicate component reference")
        if self.component_id in self.dependencies:
            raise ValueError("Component cannot depend on itself")
        return self


class ReleaseRole(Contract):
    role: ReleaseRoleName
    scope_id: Identifier
    component_id: Identifier


class ReleaseManifest(Contract):
    schema_version: Literal["release-manifest/1"] = "release-manifest/1"
    release_id: Identifier
    artifacts: tuple[ReleaseArtifact, ...] = Field(min_length=1, max_length=64)
    components: tuple[ReleaseComponent, ...] = Field(min_length=1, max_length=512)
    roles: tuple[ReleaseRole, ...] = Field(min_length=14, max_length=2048)

    @model_validator(mode="after")
    def closed_graph(self) -> Self:
        artifacts = {a.artifact_id: a for a in self.artifacts}
        components = {c.component_id: c for c in self.components}
        if len(artifacts) != len(self.artifacts) or len(components) != len(
            self.components
        ):
            raise ValueError("Release identities must be unique")
        roots = [PurePosixPath(a.root) for a in self.artifacts]
        if any(
            a == b or a in b.parents or b in a.parents
            for i, a in enumerate(roots)
            for b in roots[i + 1 :]
        ):
            raise ValueError("Artifact roots cannot overlap")
        if sum(len(a.files) for a in self.artifacts) > 100000:
            raise ValueError("Release file budget exceeded")
        used_artifacts: set[str] = set()
        for component in self.components:
            if (
                not set(component.artifact_ids) <= artifacts.keys()
                or not set(component.dependencies) <= components.keys()
            ):
                raise ValueError("Release has unresolved dependency")
            used_artifacts.update(component.artifact_ids)
        if used_artifacts != artifacts.keys():
            raise ValueError("Release contains unbound artifact")
        bindings: dict[tuple[str, str], ReleaseRole] = {}
        for role in self.roles:
            key = (role.role, role.scope_id)
            if key in bindings or role.component_id not in components:
                raise ValueError("Duplicate or unresolved role binding")
            if components[role.component_id].kind != ROLE_KIND[role.role]:
                raise ValueError("Role bound to incompatible component kind")
            if role.role in GLOBAL_ROLES and role.scope_id != "global":
                raise ValueError("Global role cannot change scope")
            bindings[key] = role
        if any((name, "global") not in bindings for name in GLOBAL_ROLES):
            raise ValueError("Release lacks a required global role")
        scopes = {r.scope_id for r in self.roles if r.role == "site"}
        if not scopes or any(
            {r.scope_id for r in self.roles if r.role == name} != scopes
            for name in SITE_ROLES
        ):
            raise ValueError(
                "Every site scope needs browser, site, evaluator and reviewer"
            )
        active: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in active:
                raise ValueError("Cyclic release dependency")
            if name in visited:
                return
            active.add(name)
            for dependency in components[name].dependencies:
                visit(dependency)
            active.remove(name)
            visited.add(name)

        for role in self.roles:
            visit(role.component_id)
        if visited != components.keys():
            raise ValueError("Release contains unreachable component")
        return self
