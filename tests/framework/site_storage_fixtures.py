"""Real original journal/CAS with explicit synthetic worker and kernel scope."""

from pathlib import Path
from lab_generate_skill.domain.native_private_json import GITLAB_PRIVATE_JSON
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from site_worker_fixtures import configuration
from evidence_session_fixtures import capacity


def private_configuration(root: Path) -> SiteWorkerConfiguration:
    base = configuration(job_id="4752096")
    files = SiteFilesPlan.model_validate(
        {
            **base.files.model_dump(),
            "workspace_root": str(root),
            "source_path": str(root / "gitlab.sif"),
            "image": base.files.image.model_copy(update={"path": "gitlab.sif"}),
        }
    )
    config = EvidenceStorageConfig(
        storage_id="original-site-artifacts",
        evidence_root=str(root / "evidence"),
        session_root=str(root / "sessions"),
        max_object_bytes=64 * 1024 * 1024,
        capacity=capacity(),
        installation=base.installation,
    )
    binding = EvidenceSessionBinding(
        storage_id=config.storage_id,
        scope="run",
        source_task_id=None,
        session_id="original-site",
        owner=base.token.owner,
        release_id=base.installation.manifest.release_id,
        storage_config_sha256=config.sha256,
    )
    plan = SitePrivateEvidencePlan(
        profile=GITLAB_PRIVATE_JSON,
        binding=binding,
        config=config,
        resource_journal_root=str(root / "journal"),
    )
    return SiteWorkerConfiguration(
        site_id="gitlab",
        token=base.token,
        files=files,
        apptainer="/usr/bin/apptainer",
        installation=base.installation,
        private_evidence=plan,
    )
