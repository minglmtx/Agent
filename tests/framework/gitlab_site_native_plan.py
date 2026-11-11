"""Inert selected original asset/private storage declarations before acquisition."""

from pathlib import Path
from gitlab_source_selection import GitlabSourceSelection
from lab_generate_skill.domain.lifecycle import ResourceOwner
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
)
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from site_worker_fixtures import configuration

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


def private_site_plan(
    owner: ResourceOwner,
    installation: ReleaseInstallation,
    *,
    evidence_root: Path,
    session_root: Path,
    journal_root: Path,
    selection: GitlabSourceSelection,
) -> SitePrivateEvidencePlan:
    if not isinstance(selection, GitlabSourceSelection):
        raise TypeError("Explicit validated GitLab selection required")
    config = EvidenceStorageConfig(
        storage_id="gitlab-native-private",
        evidence_root=str(evidence_root),
        session_root=str(session_root),
        max_object_bytes=64 * 1024 * 1024,
        capacity=EvidenceSessionCapacity(
            max_exchanges=64, max_resolutions_per_exchange=3, max_bytes=4 * 1024 * 1024
        ),
        installation=installation,
    )
    binding = EvidenceSessionBinding(
        storage_id=config.storage_id,
        scope="run",
        source_task_id=None,
        session_id="gitlab-native-private",
        owner=owner,
        release_id=installation.manifest.release_id,
        storage_config_sha256=config.sha256,
    )
    return SitePrivateEvidencePlan(
        profile=selection.profile,
        binding=binding,
        config=config,
        resource_journal_root=str(journal_root),
    )


def native_configuration(
    installation: ReleaseInstallation,
    *,
    job_id: str,
    parent: Path,
    private_evidence: SitePrivateEvidencePlan,
) -> SiteWorkerConfiguration:
    base = configuration(installation, job_id=job_id)
    if private_evidence.binding.owner.job_id != job_id:
        raise ValueError("GitLab private plan changed original allocation job")
    image = W / "assets/webarena/gitlab" / GITLAB_IMAGE_SHA / "gitlab.sif"
    return SiteWorkerConfiguration(
        site_id="gitlab",
        token=base.token.model_copy(update={"owner": private_evidence.binding.owner}),
        files=SiteFilesPlan(
            instance_id=base.token.expected_resource_id,
            workspace_root=str(W),
            source_path=str(image),
            node_root=str(parent / "instance"),
            image=ReleaseFile(
                path=image.name,
                sha256=GITLAB_IMAGE_SHA,
                size_bytes=22167199744,
                executable=False,
            ),
        ),
        apptainer="/usr/bin/apptainer",
        installation=installation,
        private_evidence=private_evidence,
    )
