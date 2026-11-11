"""Real small-tree byte copies; original image loading is separately qualified."""

import hashlib
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.read_inputs import PublishedMapInputs
from lab_generate_skill.adapters.map_runtime.stage import NodeMapInputs
from lab_generate_skill.adapters.map_runtime.tree_copy import clone_tree
from lab_generate_skill.adapters.map_runtime import tree_copy, stage
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from map_runtime_fixtures import runtime_case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_receipt_to_complete_real_private_clones(node_path: Path) -> None:
    plan = runtime_case(node_path)
    inventories = PublishedMapInputs().read(plan, guard())
    targets = node_path / "clones"
    targets.mkdir(mode=0o700)
    for declaration, inventory in zip(plan.trees, inventories, strict=True):
        target = targets / declaration.role
        clone_tree(declaration, inventory, target, guard())
        source = Path(declaration.source_root)
        for member in inventory.files:
            copied = target / member.file.path
            assert hashlib.sha256(copied.read_bytes()).hexdigest() == member.file.sha256
            assert copied.stat().st_mode & 0o777 == member.mode
            assert copied.stat().st_ino != (source / member.file.path).stat().st_ino
        assert (target / "empty-directory").is_dir()
        with pytest.raises(FileExistsError):
            clone_tree(declaration, inventory, target, guard())
        changed = target / inventory.files[0].file.path
        changed.write_bytes(b"private mutation")
        original = source / inventory.files[0].file.path
        assert (
            hashlib.sha256(original.read_bytes()).hexdigest()
            == inventory.files[0].file.sha256
        )
    assert (targets / "app/empty.lock").read_bytes() == b""
    assert (targets / "frontend/Gemfile.lock").is_file()
    assert not (targets / "frontend/node_modules").exists()


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "missing",
        "symlink",
        "fifo",
        "mode",
        "directory-as-file",
        "source-alias",
    ],
)
def test_complete_shape_errors_precede_destination(
    node_path: Path, change: str
) -> None:
    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    declaration = plan.trees[0]
    source = Path(declaration.source_root)
    path = source / "baseline.json"
    if change == "extra":
        (source / "extra").write_bytes(b"not declared")
    elif change == "missing":
        path.unlink()
    elif change == "symlink":
        path.unlink()
        path.symlink_to(source / "postgres/PG_VERSION")
    elif change == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif change == "mode":
        path.chmod(0o644)
    elif change == "directory-as-file":
        path.unlink()
        path.mkdir()
    else:
        real = source.with_name("real-app")
        source.rename(real)
        source.symlink_to(real, target_is_directory=True)
    target = node_path / "clone"
    with pytest.raises(EvidenceIntegrityError):
        clone_tree(declaration, inventory, target, guard())
    assert not target.exists()


def test_content_corruption_retains_partial_and_never_overwrites(
    node_path: Path,
) -> None:
    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    declaration = plan.trees[0]
    source = Path(declaration.source_root) / "baseline.json"
    source.write_bytes(b"x" * source.stat().st_size)
    target = node_path / "clone"
    with pytest.raises(EvidenceIntegrityError, match="bytes or identity"):
        clone_tree(declaration, inventory, target, guard())
    partial = (target / "baseline.json").read_bytes()
    assert partial == source.read_bytes()
    with pytest.raises(FileExistsError):
        clone_tree(declaration, inventory, target, guard())
    assert (target / "baseline.json").read_bytes() == partial


def test_cancellation_after_first_copy_retains_progress(node_path: Path) -> None:
    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    target = node_path / "clone"

    class Stop:
        def checkpoint(self) -> float:
            if (target / "baseline.json").exists():
                raise TimeoutError("original clone cancellation")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError, match="original clone cancellation"):
        clone_tree(plan.trees[0], inventory, target, Stop())
    assert (target / "baseline.json").exists() and not (
        target / "postgres/PG_VERSION"
    ).exists()
    with pytest.raises(FileExistsError):
        clone_tree(plan.trees[0], inventory, target, guard())


def test_whole_source_change_during_copy_refused(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    original = copy_pinned_file

    def changed(
        source: Path,
        target: Path,
        entry: ReleaseFile,
        control: OperationControl,
        **kwargs: Any,
    ) -> None:
        original(source, target, entry, control, **kwargs)
        if entry.path == "empty.lock":
            (source / "new-extra").write_bytes(b"external change")

    monkeypatch.setattr(tree_copy, "copy_pinned_file", changed)
    with pytest.raises(EvidenceIntegrityError, match="Undeclared"):
        clone_tree(plan.trees[0], inventory, node_path / "clone", guard())
    assert (node_path / "clone/empty.lock").exists()


def test_stage_orchestration_real_trees_explicit_synthetic_image_loader(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = runtime_case(node_path)
    loaded: list[ReleaseFile] = []

    def common(_self: Any, files: SiteFilesPlan, control: OperationControl) -> None:
        assert files == plan.files
        root = Path(files.node_root)
        root.mkdir(mode=0o700)
        for name in ("image", "state", "logs"):
            (root / name).mkdir(mode=0o700)
        loaded.append(files.image)

    def image(
        source: Path, target: Path, file: ReleaseFile, control: OperationControl
    ) -> None:
        expected = next(x for x in plan.images if x.file == file)
        assert str(source / file.path) == expected.source_path
        assert target == Path(plan.files.node_root) / "image"
        loaded.append(file)

    monkeypatch.setattr(NodeSiteFiles, "stage", common)
    monkeypatch.setattr(stage, "copy_pinned_file", image)
    NodeMapInputs().stage(plan, guard())
    assert {f.path for f in loaded} == {i.file.path for i in plan.images}
    assert len(loaded) == 5
    for tree in plan.trees:
        assert Path(plan.node_tree(tree.role)).is_dir()
    with pytest.raises(FileExistsError):
        NodeMapInputs().stage(plan, guard())
    assert len(loaded) == 5


def test_invalid_tree_prevents_even_image_loader(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = runtime_case(node_path)
    (Path(plan.trees[-1].source_root) / "extra").write_bytes(b"unexpected")

    def forbidden(*args: Any) -> None:
        pytest.fail("image loader preceded complete tree validation")

    monkeypatch.setattr(NodeSiteFiles, "stage", forbidden)
    with pytest.raises(EvidenceIntegrityError):
        NodeMapInputs().stage(plan, guard())
    assert not Path(plan.files.node_root).exists()
