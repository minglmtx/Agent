"""Tiny frozen files for content/graph validation, not a runnable project release."""

import hashlib
from pathlib import Path
from lab_generate_skill.domain.release import (
    ReleaseManifest,
    ReleaseArtifact,
    ReleaseFile,
    ReleaseComponent,
    ReleaseRole,
    GLOBAL_ROLES,
    SITE_ROLES,
    ROLE_KIND,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference


def manifest(root: Path) -> ReleaseManifest:
    files = (
        ReleaseFile(
            path="module.py",
            sha256=hashlib.sha256(b"code").hexdigest(),
            size_bytes=4,
            executable=False,
        ),
        ReleaseFile(
            path="bin/worker",
            sha256=hashlib.sha256(b"run").hexdigest(),
            size_bytes=3,
            executable=True,
        ),
    )
    roles = sorted(GLOBAL_ROLES | SITE_ROLES)
    components = tuple(
        ReleaseComponent.model_validate(
            dict(
                component_id=name,
                kind=ROLE_KIND[name],
                interface_id="unit-" + name,
                contract_version="1.0",
                artifact_ids=("files",),
                dependencies=(() if name == "code" else ("code",)),
            )
        )
        for name in roles
    )
    return ReleaseManifest(
        release_id="release-1",
        artifacts=(ReleaseArtifact(artifact_id="files", root=str(root), files=files),),
        components=components,
        roles=tuple(
            ReleaseRole.model_validate(
                dict(
                    role=name,
                    scope_id="global" if name in GLOBAL_ROLES else "unit-site",
                    component_id=name,
                )
            )
            for name in roles
        ),
    )


def frozen(root: Path) -> ReleaseManifest:
    root.mkdir()
    (root / "bin").mkdir()
    (root / "module.py").write_bytes(b"code")
    (root / "module.py").chmod(0o444)
    (root / "bin/worker").write_bytes(b"run")
    (root / "bin/worker").chmod(0o555)
    (root / "bin").chmod(0o555)
    root.chmod(0o555)
    return manifest(root)


def reference(raw: bytes) -> EvidenceRef:
    return evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="release-manifest/1",
            visibility="private",
            producer="unit-release",
        ),
    )
