"""The same pinned installed site plan for startup diagnosis and whole tasks."""

from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from site_worker_fixtures import configuration
from test_admin_database_native import IMAGE, IMAGE_SHA
from shopping_image_live import IMAGE as SHOPPING_IMAGE, SHA as SHOPPING_SHA


def startup_seconds(
    site_id: Literal["shopping_admin", "shopping", "gitlab", "reddit"],
) -> int:
    # The registered single-CPU Shopping reproduction spent133s on the43GB
    # verified image and24s on seed before ~80s native search startup. Its
    # original240s cannot include configuration/frontend. New operations only.
    if site_id in ("shopping", "gitlab", "reddit"):
        return 600
    if site_id == "shopping_admin":
        return 240
    raise ValueError("Unsupported fixed native startup budget")


def native_configuration(
    installation: ReleaseInstallation,
    *,
    job_id: str,
    parent: Path,
    site_id: Literal["shopping_admin", "shopping", "gitlab", "reddit"],
    private_evidence: SitePrivateEvidencePlan | None = None,
) -> SiteWorkerConfiguration:
    if site_id == "reddit":
        if private_evidence is None:
            raise ValueError("Reddit requires predeclared original private evidence")
        from reddit_site_native_plan import native_configuration as reddit_configuration

        return reddit_configuration(
            installation,
            job_id=job_id,
            parent=parent,
            private_evidence=private_evidence,
        )
    if site_id == "gitlab":
        if private_evidence is None:
            raise ValueError("GitLab requires predeclared original private evidence")
        from gitlab_site_native_plan import native_configuration as gitlab_configuration

        return gitlab_configuration(
            installation,
            job_id=job_id,
            parent=parent,
            private_evidence=private_evidence,
        )
    if private_evidence is not None:
        raise ValueError("Private native artifacts are not declared for this site")
    base = configuration(installation, job_id=job_id)
    image = SHOPPING_IMAGE if site_id == "shopping" else IMAGE
    return SiteWorkerConfiguration.model_validate(
        {
            **base.model_dump(),
            "site_id": site_id,
            "files": SiteFilesPlan(
                instance_id=base.token.expected_resource_id,
                workspace_root="/anvme/workspace/r102bf10-lab-generate-skill",
                source_path=str(image),
                node_root=str(parent / "instance"),
                image=ReleaseFile(
                    path=image.name,
                    sha256=SHOPPING_SHA if site_id == "shopping" else IMAGE_SHA,
                    size_bytes=43470442496 if site_id == "shopping" else 1356492800,
                    executable=False,
                ),
            ),
        }
    )
