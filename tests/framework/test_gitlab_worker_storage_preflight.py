"""Reject missing guard and retain uncertain startup before native effects."""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.bootstrap.gitlab_group_lifecycle import build_group_lifecycle
from lab_generate_skill.sites.gitlab.worker_instance import GitlabWorkerInstance
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from gitlab_site_storage_live import missing_asset_configuration
from storage_installation_fixtures import storage_installation
from test_gitlab_instance import instance
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_missing_asset_plan_is_inert_and_requires_original_live_guard(
    tmp_path: Path,
) -> None:
    config = missing_asset_configuration(
        storage_installation(),
        job_id="4752096",
        root=tmp_path,
        parent=Path("/tmp/unique-gitlab-worker"),
    )
    assert (
        SiteWorkerConfiguration.model_validate_json(config.model_dump_json()) == config
    )
    with pytest.raises(ValueError, match="original live worker guard"):
        build_site_instance(config)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("cancelled", [False, True])
def test_uncertain_storage_initialization_never_stages_native_or_restarts(
    node_path: Path, tmp_path: Path, cancelled: bool
) -> None:
    site, _, _, _ = instance(node_path)
    config = missing_asset_configuration(
        storage_installation(),
        job_id="4752096",
        root=tmp_path,
        parent=node_path / "node",
    )
    site.files_plan = config.files
    original = (
        OperationStopped("CANCELLED", "original-storage")
        if cancelled
        else OSError("unknown create reply")
    )

    class Artifacts:
        calls = 0
        stopped = False

        def initialize(self, control: OperationControl) -> None:
            self.calls += 1
            raise original

        def stop_new_io(self) -> None:
            self.stopped = True

    artifacts = Artifacts()
    worker = GitlabWorkerInstance(
        config,
        site,
        cast(SitePrivateArtifacts, artifacts),
        cast(NativeInputCommands, None),
        lambda control: "unused",
        group_lifecycle_factory=build_group_lifecycle,
    )
    with pytest.raises(type(original)) as caught:
        worker.start(guard())
    assert caught.value is original and site.state == "new" and not site.generations
    assert not Path(config.files.node_root).exists()
    with pytest.raises(InvalidTransition):
        worker.start(guard())
    assert artifacts.calls == 1
    assert worker.stop(guard()) == () and artifacts.stopped
    with pytest.raises(InvalidTransition):
        worker.start(guard())
