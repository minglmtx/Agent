"""Fresh selected worker plan; no native asset access during preparation."""

from pathlib import Path
from lab_generate_skill.domain.native_private_json import GITLAB_PRIVATE_JSON
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.release import ReleaseFile
from site_worker_fixtures import configuration
from evidence_session_fixtures import capacity


def missing_asset_configuration(
    installation: ReleaseInstallation, *, job_id: str, root: Path, parent: Path
) -> SiteWorkerConfiguration:
    base = configuration(installation, job_id=job_id)
    config = EvidenceStorageConfig(
        storage_id="original-gitlab-private",
        evidence_root=str(root / "evidence"),
        session_root=str(root / "sessions"),
        max_object_bytes=64 * 1024 * 1024,
        capacity=capacity(),
        installation=installation,
    )
    binding = EvidenceSessionBinding(
        storage_id=config.storage_id,
        scope="run",
        source_task_id=None,
        session_id="original-gitlab-private",
        owner=base.token.owner,
        release_id=installation.manifest.release_id,
        storage_config_sha256=config.sha256,
    )
    return SiteWorkerConfiguration(
        site_id="gitlab",
        token=base.token,
        files=SiteFilesPlan(
            instance_id=base.token.expected_resource_id,
            workspace_root=str(root),
            source_path=str(root / "intentionally-missing" / "gitlab.sif"),
            node_root=str(parent / "instance"),
            image=ReleaseFile(
                path="gitlab.sif", sha256="0" * 64, size_bytes=1, executable=False
            ),
        ),
        installation=installation,
        apptainer="/usr/bin/apptainer",
        private_evidence=SitePrivateEvidencePlan(
            profile=GITLAB_PRIVATE_JSON,
            config=config,
            binding=binding,
            resource_journal_root=str(root / "journal"),
        ),
    )
