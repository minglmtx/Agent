"""Synthetic versioned metadata; does not import or implement native sites."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.registration import (
    RegistryManifest,
    RegistryComponent,
    TaskRegistration,
    SupportedInterface,
)
from lab_generate_skill.domain.release import (
    ReleaseManifest,
    ReleaseComponent,
    ReleaseFile,
    ReleaseArtifact,
    ReleaseRole,
)
from lab_generate_skill.domain.evidence import (
    EvidenceMetadata,
    EvidenceRequirements,
    EvidenceRequirement,
    EvidenceRef,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.registry.resolve import TaskRegistry
from release_fixtures import manifest as base_release


def facts() -> EvidenceRequirements:
    return EvidenceRequirements(
        facts=(
            EvidenceRequirement(
                name="state", content_schema="customer-state/1", visibility="private"
            ),
        ),
        events=("before_action", "after_action"),
    )


@dataclass
class Fixture:
    index: RegistryManifest
    release: ReleaseManifest
    reference: EvidenceRef
    supported: tuple[SupportedInterface, ...]

    def registry(self) -> TaskRegistry:
        return TaskRegistry(self.index, self.reference, self.release, self.supported)


def fixture(root: Path) -> Fixture:
    release = base_release(root / "code")
    roles = {
        "site": "site",
        "task_adapter": "task",
        "collector": "collector",
        "evaluator": "evaluator",
        "evidence_schema": "schema",
        "recovery": "recovery",
        "reviewer": "reviewer",
        "browser": "browser",
        "actor_protocol": "actor_protocol",
    }
    components: list[RegistryComponent] = []
    for kind, name in roles.items():
        interface = {
            "evidence_schema": "customer-state",
            "recovery": "customer-reset",
            "actor_protocol": "browser-actions",
        }.get(kind, "unit-" + kind)
        module = "lab_generate_skill.sites.shopping_admin." + name
        entry = ReleaseFile(
            path=module.replace(".", "/") + ".py",
            size_bytes=4,
            sha256=hashlib.sha256(b"code").hexdigest(),
            executable=False,
        )
        components.append(
            RegistryComponent.model_validate(
                dict(
                    component_id=name,
                    kind=kind,
                    interface_id=interface,
                    contract_version="1.0",
                    artifact_id="files",
                    implementation=entry,
                    entrypoint=module + ":Factory",
                    provides_capabilities=(
                        ("persisted_mutation",) if kind == "site" else ()
                    ),
                    requires_capabilities=(),
                    provides_evidence=(
                        facts()
                        if kind in ("site", "collector", "evidence_schema")
                        else EvidenceRequirements()
                    ),
                    requires_evidence=(
                        facts()
                        if kind in ("evaluator", "reviewer")
                        else EvidenceRequirements()
                    ),
                )
            )
        )
    registration = TaskRegistration(
        site="shopping_admin",
        family="customer_create",
        contract_version=1,
        registration_id="customer-create-v1",
        site_provider="site",
        task_adapter="task",
        collector="collector",
        evaluator="evaluator",
        evidence_schema_provider="schema",
        evidence_schema="customer-state/1",
        recovery_provider="recovery",
        recovery_contract="customer-reset/1",
        reviewer="reviewer",
        actor_protocol="browser-actions/1",
        required_capabilities=("persisted_mutation",),
    )
    index = RegistryManifest(
        registry_id="registry-1",
        release_id=release.release_id,
        registrations=(registration,),
        components=tuple(components),
    )
    return bind(index, release)


def bind(index: RegistryManifest, base: ReleaseManifest) -> Fixture:
    raw = index.model_dump_json().encode()
    reference = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="task-registry/1",
            visibility="private",
            producer="unit-registry",
        ),
    )
    metadata = {c.component_id: c for c in index.components}
    release_components = [c for c in base.components if c.component_id not in metadata]
    release_components = [
        (
            c.model_copy(update={"dependencies": tuple(sorted(metadata))})
            if c.kind == "registry"
            else c
        )
        for c in release_components
    ]
    release_components.extend(
        ReleaseComponent(
            component_id=c.component_id,
            kind=c.kind,
            interface_id=c.interface_id,
            contract_version=c.contract_version,
            artifact_ids=(c.artifact_id,),
            dependencies=("code",),
        )
        for c in index.components
    )
    files = tuple(c.implementation for c in index.components) + (
        ReleaseFile(
            path="registry.json",
            sha256=reference.sha256,
            size_bytes=reference.size_bytes,
            executable=False,
        ),
    )
    files += tuple(
        f
        for f in base.artifacts[0].files
        if f.path not in {entry.path for entry in files}
    )
    artifact = ReleaseArtifact(
        artifact_id="files", root=base.artifacts[0].root, files=files
    )
    roles = [
        r
        for r in base.roles
        if r.role not in ("site", "browser", "evaluator", "reviewer")
    ]
    for r in index.registrations:
        roles.extend(
            ReleaseRole.model_validate(
                dict(role=kind, scope_id=r.registration_id, component_id=name)
            )
            for kind, name in (
                ("site", r.site_provider),
                ("browser", "browser"),
                ("evaluator", r.evaluator),
                ("reviewer", r.reviewer),
            )
        )
    release = ReleaseManifest(
        release_id=index.release_id,
        artifacts=(artifact,),
        components=tuple(release_components),
        roles=tuple(roles),
    )
    supported = tuple(
        SupportedInterface(
            interface_id=c.interface_id,
            contract_major=int(c.contract_version.split(".")[0]),
        )
        for c in index.components
    )
    return Fixture(index, release, reference, tuple(dict.fromkeys(supported)))
