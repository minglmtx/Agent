"""Storage assembly is inert; failed/late-cancel initialization is never replayed."""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.bootstrap.site_private_artifacts import (
    build_site_private_artifacts,
)
from lab_generate_skill.adapters.sites.private_artifacts import (
    OriginalSitePrivateArtifacts,
)
from lab_generate_skill.adapters.sites.storage_admission import (
    OriginalSiteStorageAdmission,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from site_storage_fixtures import private_configuration
from test_slurm_commands import guard


class InitStore:
    calls = 0
    committed = False
    failure: BaseException | None = None

    def initialize(self, control: OperationControl) -> None:
        self.calls += 1
        control.checkpoint()
        self.committed = True
        if self.failure is not None:
            raise self.failure


class StoppedAdmission:
    stopped = False

    def stop_new_io(self) -> None:
        self.stopped = True


@pytest.mark.parametrize("failure", ["native_failure", "after_commit_cancel"])
def test_uncertain_initialization_cannot_bind_or_issue_a_second_init(
    tmp_path: Path, failure: str
) -> None:
    cfg = private_configuration(tmp_path)
    plan = cfg.private_evidence
    assert plan is not None
    store = InitStore()
    admission = StoppedAdmission()
    error = OSError("original init failed")
    if failure == "native_failure":
        store.failure = error

    class Control:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if failure == "after_commit_cancel" and self.calls == 2:
                raise OperationStopped("CANCELLED", "known-initialization")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    artifacts = OriginalSitePrivateArtifacts(
        plan,
        cast(ManagedEvidenceStore, store),
        cast(OriginalSiteStorageAdmission, admission),
    )
    with pytest.raises(
        OSError if failure == "native_failure" else OperationStopped
    ) as caught:
        artifacts.initialize(Control())
    if failure == "native_failure":
        assert caught.value is error
    assert store.committed and store.calls == 1 and not artifacts.initialized
    with pytest.raises(InvalidTransition):
        artifacts.initialize(guard())
    artifacts.stop_new_io()
    artifacts.stop_new_io()
    assert admission.stopped and store.calls == 1


def test_original_controller_assembly_does_not_create_any_storage(
    tmp_path: Path,
) -> None:
    cfg = private_configuration(tmp_path)
    before = list(tmp_path.iterdir())
    artifacts = build_site_private_artifacts(cfg, "controller", None, guard())
    assert not artifacts.attempted and not artifacts.initialized
    assert list(tmp_path.iterdir()) == before
    artifacts.stop_new_io()
    with pytest.raises(InvalidTransition):
        artifacts.initialize(guard())
    assert list(tmp_path.iterdir()) == before
