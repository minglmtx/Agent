"""Exact task-family composition and packaged implementation declarations.

Registry metadata grants no runtime permission. Capabilities and evidence are
claims checked against release declarations; native integrations verify behavior.
"""

from typing import Annotated, Literal, Self
from pydantic import Field, StringConstraints, model_validator
from .validation import Contract, Identifier
from .identity import Site
from .evidence import EvidenceRequirements
from .release import ReleaseFile, ReleaseKind

ProtocolName = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*/[1-9][0-9]*$")
]


class RegistrationKey(Contract):
    site: Site
    family: Identifier
    contract_version: int = Field(ge=1)


class TaskRegistration(RegistrationKey):
    schema_version: Literal["task-registration/1"] = "task-registration/1"
    registration_id: Identifier
    site_provider: Identifier
    task_adapter: Identifier
    collector: Identifier
    evaluator: Identifier
    evidence_schema_provider: Identifier
    evidence_schema: ProtocolName
    recovery_provider: Identifier
    recovery_contract: ProtocolName
    reviewer: Identifier
    actor_protocol: ProtocolName
    required_capabilities: tuple[Identifier, ...] = Field(max_length=128)

    @property
    def key(self) -> RegistrationKey:
        return RegistrationKey(
            site=self.site, family=self.family, contract_version=self.contract_version
        )

    @model_validator(mode="after")
    def unique_capabilities(self) -> Self:
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("Duplicate required task capability")
        return self


class RegistryComponent(Contract):
    component_id: Identifier
    kind: ReleaseKind
    interface_id: Identifier
    contract_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+$")
    artifact_id: Identifier
    implementation: ReleaseFile
    entrypoint: str = Field(
        pattern=r"^lab_generate_skill\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
    )
    provides_capabilities: tuple[Identifier, ...] = Field(max_length=128)
    requires_capabilities: tuple[Identifier, ...] = Field(max_length=128)
    provides_evidence: EvidenceRequirements
    requires_evidence: EvidenceRequirements

    @model_validator(mode="after")
    def package_entry(self) -> Self:
        module, _ = self.entrypoint.split(":")
        parts = module.split(".")
        if (
            "scripts" in parts
            or "experiments" in parts
            or parts[1]
            not in {
                "sites",
                "evaluators",
                "task_families",
                "adapters",
                "actor",
                "teacher",
                "generator",
                "runtime",
                "policies",
            }
        ):
            raise ValueError("Entry must use a declared implementation package")
        file = self.implementation.path
        suffix = module.replace(".", "/")
        if not any(
            file == candidate or file.endswith("/" + candidate)
            for candidate in (suffix + ".py", suffix + "/__init__.py")
        ):
            raise ValueError("Entry module differs from pinned source file")
        for values in (self.provides_capabilities, self.requires_capabilities):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate component capability")
        return self


class SupportedInterface(Contract):
    interface_id: Identifier
    contract_major: int = Field(ge=1)


class RegistryManifest(Contract):
    schema_version: Literal["task-registry/1"] = "task-registry/1"
    registry_id: Identifier
    release_id: Identifier
    registrations: tuple[TaskRegistration, ...] = Field(min_length=1, max_length=8192)
    components: tuple[RegistryComponent, ...] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        if len({r.registration_id for r in self.registrations}) != len(
            self.registrations
        ) or len({r.key for r in self.registrations}) != len(self.registrations):
            raise ValueError("Registration ID and site/family/version must be unique")
        if len({c.component_id for c in self.components}) != len(self.components):
            raise ValueError("Registry component ID must be unique")
        return self


class ResolvedRegistration(Contract):
    registration: TaskRegistration
    components: tuple[RegistryComponent, ...]
