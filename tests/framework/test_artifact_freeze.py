"""Pinned byte copy, immutable replay, invalid input and publication boundaries."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from artifact_freeze_fixtures import fixture
from test_slurm_commands import guard


def test_actual_freeze_preserves_bytes_exec_and_source_then_reuses(
    tmp_path: Path,
) -> None:
    freezer, source = fixture(tmp_path)
    before = {
        p: (p.read_bytes(), p.stat().st_mode)
        for p in Path(source.root).rglob("*")
        if p.is_file()
    }
    result = freezer.freeze(source, "v1", guard())
    root = Path(result.root)
    assert result.files == source.files and root == tmp_path / "published/v1"
    for entry in result.files:
        assert (root / entry.path).read_bytes() == (
            Path(source.root) / entry.path
        ).read_bytes()
        assert not (root / entry.path).stat().st_mode & 0o222
        assert bool((root / entry.path).stat().st_mode & 0o111) == entry.executable
    assert all(not path.stat().st_mode & 0o222 for path in (root, root / "nested"))
    assert freezer.freeze(source, "v1", guard()) == result
    assert before == {p: (p.read_bytes(), p.stat().st_mode) for p in before}


@pytest.mark.parametrize("identifier", ["", "../escape", "a/b", None, 1])
def test_invalid_identity_has_no_destination(
    tmp_path: Path, identifier: object
) -> None:
    freezer, source = fixture(tmp_path)
    with pytest.raises(ValidationError):
        freezer.freeze(source, identifier, guard())  # type: ignore[arg-type]
    assert not list((tmp_path / "published").iterdir())


@pytest.mark.parametrize(
    "fault", ["extra", "missing", "link", "directory_link", "fifo"]
)
def test_bad_source_inventory_fails_before_creation(tmp_path: Path, fault: str) -> None:
    freezer, source = fixture(tmp_path)
    root = Path(source.root)
    if fault == "extra":
        (root / "extra").write_bytes(b"extra")
    elif fault == "missing":
        (root / "empty").unlink()
    elif fault == "link":
        (root / "alias").symlink_to(root / "empty")
    elif fault == "directory_link":
        (root / "alias").symlink_to(root / "nested", target_is_directory=True)
    else:
        os.mkfifo(root / "fifo")
    with pytest.raises(EvidenceIntegrityError):
        freezer.freeze(source, "v1", guard())
    assert not list((tmp_path / "published").iterdir())


@pytest.mark.parametrize("fault", ["hash", "size", "mode"])
def test_wrong_source_pin_preserves_unpublished_candidate(
    tmp_path: Path, fault: str
) -> None:
    freezer, source = fixture(tmp_path)
    path = Path(source.root) / "nested/data.bin"
    if fault == "hash":
        path.write_bytes(b"different!!")
    elif fault == "size":
        path.write_bytes(b"x")
    else:
        path.chmod(0o755)
    with pytest.raises(EvidenceIntegrityError) as error:
        freezer.freeze(source, "v1", guard())
    observation = getattr(error.value, "artifact_freeze")
    assert observation.destination_created
    assert Path(observation.artifact.root) == tmp_path / "published/v1"
    assert (tmp_path / "published/v1").exists()


@pytest.mark.parametrize("existing", ["empty", "foreign", "link"])
def test_existing_target_is_never_overwritten(tmp_path: Path, existing: str) -> None:
    freezer, source = fixture(tmp_path)
    target = tmp_path / "published/v1"
    if existing == "link":
        target.symlink_to(source.root, target_is_directory=True)
    else:
        target.mkdir()
        if existing == "foreign":
            (target / "keep").write_bytes(b"original")
    with pytest.raises(EvidenceIntegrityError) as error:
        freezer.freeze(source, "v1", guard())
    assert not getattr(error.value, "artifact_freeze").destination_created
    if existing == "foreign":
        assert (target / "keep").read_bytes() == b"original"
    if existing == "link":
        assert target.is_symlink()


def test_overlap_and_non_workspace_source_are_rejected(tmp_path: Path) -> None:
    freezer, source = fixture(tmp_path)
    bad = FileArtifactFreezer(tmp_path, Path(source.root))
    with pytest.raises(ValueError, match="overlap"):
        bad.freeze(source, "v1", guard())
    with pytest.raises(ValueError):
        FileArtifactFreezer(tmp_path, tmp_path.parent)


def test_stop_before_work_has_no_destination(tmp_path: Path) -> None:
    freezer, source = fixture(tmp_path)

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("cancelled", "unit")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        freezer.freeze(source, "v1", Stopped())
    assert not list((tmp_path / "published").iterdir())
