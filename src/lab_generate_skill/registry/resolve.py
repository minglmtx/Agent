"""Exact immutable registration lookup; no imports, I/O or site branches.

Input is canonical registry evidence and the complete original release. Bind
all metadata up front, then resolve TaskBinding by exact tuple AND registered ID.
Only bootstrap may instantiate the returned pinned package entries.
"""

import hashlib
from types import MappingProxyType
from .compatibility import check_composition
from lab_generate_skill.domain.registration import (
    RegistrationKey,
    RegistryManifest,
    RegistryComponent,
    SupportedInterface,
    ResolvedRegistration,
)
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict


class RegistrationNotFound(LookupError):
    """No exact task family/version exists; never select a nearest match."""


class TaskRegistry:
    def __init__(
        self,
        manifest: RegistryManifest,
        reference: EvidenceRef,
        release: ReleaseManifest,
        supported: tuple[SupportedInterface, ...],
    ) -> None:
        manifest, release = RegistryManifest.model_validate(
            manifest
        ), ReleaseManifest.model_validate(release)
        reference = EvidenceRef.model_validate(reference)
        private_state_ref(reference, "task-registry/1")
        raw = manifest.model_dump_json().encode()
        if (
            len(raw) > 8 * 1024 * 1024
            or reference.size_bytes != len(raw)
            or reference.sha256 != hashlib.sha256(raw).hexdigest()
        ):
            raise EvidenceIntegrityError(
                "Registry differs from canonical original evidence"
            )
        if manifest.release_id != release.release_id:
            raise OwnershipConflict("Registry belongs to another release")
        if type(supported) is not tuple or not supported:
            raise ValueError("Bootstrap must explicitly declare supported interfaces")
        supported = tuple(SupportedInterface.model_validate(x) for x in supported)
        accepted = {(x.interface_id, x.contract_major) for x in supported}
        if len(accepted) != len(supported):
            raise ValueError("Duplicate supported interface")
        declared = {c.component_id: c for c in release.components}
        artifacts = {a.artifact_id: a for a in release.artifacts}
        roles: dict[tuple[str, str], str] = {
            (r.role, r.scope_id): r.component_id for r in release.roles
        }
        registry_component = declared[roles[("registry", "global")]]
        if not any(
            f.sha256 == reference.sha256 and f.size_bytes == reference.size_bytes
            for a in registry_component.artifact_ids
            for f in artifacts[a].files
        ):
            raise EvidenceIntegrityError("Registry evidence is not pinned by release")
        components = {c.component_id: c for c in manifest.components}
        for component in manifest.components:
            original = declared.get(component.component_id)
            if original is None or (
                original.kind,
                original.interface_id,
                original.contract_version,
            ) != (component.kind, component.interface_id, component.contract_version):
                raise ValueError(
                    "Registry implementation differs from release contract"
                )
            if (
                component.artifact_id not in original.artifact_ids
                or component.implementation
                not in artifacts[component.artifact_id].files
            ):
                raise EvidenceIntegrityError(
                    "Registry source file differs from release pin"
                )
            if (
                component.interface_id,
                int(component.contract_version.split(".")[0]),
            ) not in accepted:
                raise ValueError("Bootstrap does not support component contract major")
        resolved: dict[RegistrationKey, ResolvedRegistration] = {}
        used: set[str] = set()
        for registration in manifest.registrations:
            selected = check_composition(registration, roles, components)
            used.update(c.component_id for c in selected)
            resolved[registration.key] = ResolvedRegistration(
                registration=registration, components=selected
            )
        if used != components.keys():
            raise ValueError("Registry contains unused implementation metadata")
        self.manifest, self.reference = manifest, reference
        self._resolved = MappingProxyType(resolved)

    def lookup(self, key: RegistrationKey) -> ResolvedRegistration:
        key = RegistrationKey.model_validate(key)
        try:
            return self._resolved[key]
        except KeyError as error:
            raise RegistrationNotFound(
                "No exact site/family/contract_version registration"
            ) from error

    def resolve(self, task: TaskBinding) -> ResolvedRegistration:
        task = TaskBinding.model_validate(task)
        result = self.lookup(
            RegistrationKey(
                site=task.identity.site,
                family=task.identity.family,
                contract_version=task.identity.contract_version,
            )
        )
        if result.registration.registration_id != task.registration_id:
            raise OwnershipConflict("Task binding uses a different registration ID")
        return result
