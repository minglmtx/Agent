"""Original pinned staging, retained partial effects and pre-effect validation."""

import hashlib
import os
from pathlib import Path
from typing import Any
import pytest
from site_instance_fixtures import node_path
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from test_slurm_commands import guard


def plan(node_path: Path, **updates: Any) -> SiteFilesPlan:
    workspace = node_path / "workspace"
    workspace.mkdir(exist_ok=True)
    source = workspace / "admin.sif"
    if not source.exists():
        source.write_bytes(b"pinned engineering image bytes")
    values = dict(
        instance_id="site-1",
        workspace_root=str(workspace),
        source_path=str(source),
        node_root=str(node_path / "instance"),
        image=ReleaseFile(
            path=source.name,
            size_bytes=source.stat().st_size,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            executable=False,
        ),
    )
    values.update(updates)
    return SiteFilesPlan.model_validate(values)


def test_stage_immutable_copy_and_private_empty_directories(node_path: Path) -> None:
    spec = plan(node_path)
    NodeSiteFiles().stage(spec, guard())
    image = Path(spec.image_path)
    assert image.read_bytes() == Path(spec.source_path).read_bytes()
    assert image.stat().st_ino != Path(spec.source_path).stat().st_ino
    assert image.stat().st_mode & 0o777 == 0o444
    for directory in [spec.node_root, spec.state_root, spec.log_root]:
        assert Path(directory).stat().st_mode & 0o777 == 0o700
    assert not list(Path(spec.state_root).iterdir())
    assert not list(Path(spec.log_root).iterdir())
    with pytest.raises(FileExistsError):
        NodeSiteFiles().stage(spec, guard())
    assert image.read_bytes() == Path(spec.source_path).read_bytes()


@pytest.mark.parametrize(
    "updates",
    [
        {"node_root": "/tmp"},
        {"node_root": "/home/example"},
        {"node_root": "/tmp/../tmp/site"},
        {"source_path": "/outside/image.sif"},
        {"workspace_root": "/"},
        {"node_root": "relative"},
        {"node_root": "/tmp/a:b"},
        {"source_path": None},
        {"instance_id": ""},
        {"image": {}},
    ],
)
def test_bad_plan_refused_without_node_effect(
    node_path: Path, updates: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        plan(node_path, **updates)
    assert not (node_path / "instance").exists()


@pytest.mark.parametrize("change", ["zero", "executable", "basename"])
def test_invalid_image_pin_refused_before_stage(node_path: Path, change: str) -> None:
    spec = plan(node_path)
    values = spec.image.model_dump()
    changes: dict[str, Any] = (
        {"size_bytes": 0}
        if change == "zero"
        else {"executable": True} if change == "executable" else {"path": "another.sif"}
    )
    values.update(changes)
    with pytest.raises(ValueError):
        SiteFilesPlan(**{**spec.model_dump(), "image": ReleaseFile(**values)})
    assert not Path(spec.node_root).exists()


@pytest.mark.parametrize("which", ["source", "workspace", "parent"])
def test_symlink_ancestor_or_source_refused_before_root(
    node_path: Path, which: str
) -> None:
    spec = plan(node_path)
    if which == "source":
        path = Path(spec.source_path)
        path.rename(path.with_suffix(".original"))
        path.symlink_to(path.with_suffix(".original"))
    elif which == "workspace":
        path = Path(spec.workspace_root)
        real = node_path / "real-workspace"
        path.rename(real)
        path.symlink_to(real, target_is_directory=True)
    else:
        alias = node_path / "alias"
        alias.symlink_to(node_path, target_is_directory=True)
        spec = SiteFilesPlan(
            **{**spec.model_dump(), "node_root": str(alias / "instance")}
        )
    with pytest.raises(EvidenceIntegrityError):
        NodeSiteFiles().stage(spec, guard())
    assert not (node_path / "instance").exists()


def test_existing_root_contents_untouched(node_path: Path) -> None:
    spec = plan(node_path)
    root = Path(spec.node_root)
    root.mkdir()
    (root / "keep").write_bytes(b"original")
    with pytest.raises(FileExistsError):
        NodeSiteFiles().stage(spec, guard())
    assert [p.name for p in root.iterdir()] == ["keep"]
    assert (root / "keep").read_bytes() == b"original"


def test_wrong_digest_retains_partial_and_cannot_restage(node_path: Path) -> None:
    spec = plan(node_path)
    Path(spec.source_path).write_bytes(b"x" * spec.image.size_bytes)
    with pytest.raises(EvidenceIntegrityError):
        NodeSiteFiles().stage(spec, guard())
    assert Path(spec.image_path).read_bytes() == b"x" * spec.image.size_bytes
    with pytest.raises(FileExistsError):
        NodeSiteFiles().stage(spec, guard())


class Stop:
    def __init__(self, limit: int) -> None:
        self.limit = limit

    def checkpoint(self) -> float:
        self.limit -= 1
        if self.limit == 0:
            raise TimeoutError("original staging stop")
        return 10.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


@pytest.mark.parametrize("at", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
def test_cancel_retains_exact_progress_without_restart(
    node_path: Path, at: int
) -> None:
    spec = plan(node_path)
    with pytest.raises(TimeoutError):
        NodeSiteFiles().stage(spec, Stop(at))
    assert Path(spec.source_path).read_bytes() == b"pinned engineering image bytes"
    if at <= 2:
        assert not Path(spec.node_root).exists()
    else:
        assert Path(spec.node_root).is_dir()
        with pytest.raises(FileExistsError):
            NodeSiteFiles().stage(spec, guard())


def test_copy_and_close_faults_are_preserved_by_staging(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = plan(node_path)
    original_close = os.close
    primary, cleanup = OSError("write failed"), OSError("close uncertain")

    def fail_write(fd: int, data: Any) -> int:
        raise primary

    def fail_close(fd: int) -> None:
        original_close(fd)
        raise cleanup

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", fail_write)
        patch.setattr(os, "close", fail_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            NodeSiteFiles().stage(spec, guard())
        assert caught.value.exceptions == (primary, cleanup, cleanup)
    assert Path(spec.image_path).exists() and Path(spec.source_path).exists()


def test_directory_sync_failure_retains_complete_image(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = plan(node_path)

    def failed(path: Path) -> None:
        raise OSError("directory fsync failed")

    from lab_generate_skill.adapters.sites import files

    monkeypatch.setattr(files, "sync_directory", failed)
    with pytest.raises(OSError, match="fsync"):
        NodeSiteFiles().stage(spec, guard())
    assert Path(spec.image_path).read_bytes() == Path(spec.source_path).read_bytes()
