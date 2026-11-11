"""Fixed original public photo pins, assembled as private browser delivery input."""

from lab_generate_skill.domain.browser_task_files import BrowserTaskFilesPlan
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.sites.reddit.tasks.image_parameters import PHOTOS

WORKSPACE = "/anvme/workspace/r102bf10-lab-generate-skill"
PHOTO_ROOT = (
    WORKSPACE
    + "/experiments/sft-reddit-native-media-formal-integration-v1/codebase/scripts/native_media"
)


def reddit_photo_plan(scope: StateScope, staging_root: str) -> BrowserTaskFilesPlan:
    scope = StateScope.model_validate_json(scope.model_dump_json())
    task = scope.task
    if (task.site, task.family, task.contract_version, task.split) != (
        "reddit",
        "native_image_submission",
        1,
        "train",
    ):
        raise ValueError(
            "Only the selected original Reddit native-image family supported"
        )
    return BrowserTaskFilesPlan(
        scope=scope,
        workspace_root=WORKSPACE,
        source=ReleaseArtifact(
            artifact_id="original-reddit-public-photos-v1",
            root=PHOTO_ROOT,
            files=tuple(
                ReleaseFile(
                    path=p.relative_file,
                    sha256=p.sha256,
                    size_bytes=p.bytes,
                    executable=False,
                )
                for p in PHOTOS
            ),
        ),
        staging_root=staging_root,
    )
