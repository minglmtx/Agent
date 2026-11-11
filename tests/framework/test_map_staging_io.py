"""Small real files exercise the changed production staging/copy path, no native dataset."""

from collections import Counter
from pathlib import Path
import os
import stat
import threading
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime import tree_copy
from lab_generate_skill.adapters.map_runtime import stage as stage_module
from lab_generate_skill.adapters.map_runtime.stage import NodeMapInputs
from lab_generate_skill.adapters.map_runtime.read_inputs import PublishedMapInputs
from lab_generate_skill.adapters.releases import artifact_copy
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from map_runtime_fixtures import runtime_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def images(monkeypatch: pytest.MonkeyPatch, plan: Any) -> None:
    # Original image loader has its own immutable proof. Only image I/O is a
    # declared unit premise; all five data trees use the actual production code.
    def common(_self: Any, files: SiteFilesPlan, control: OperationControl) -> None:
        assert files == plan.files
        root = Path(files.node_root)
        root.mkdir(mode=0o700)
        for name in ("image", "state", "logs"):
            (root / name).mkdir(mode=0o700)

    monkeypatch.setattr(NodeSiteFiles, "stage", common)
    monkeypatch.setattr(stage_module, "copy_pinned_file", lambda *args: None)


def test_whole_stage_two_inspections_one_mode_sync_and_owner_thread(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = runtime_case(node_path)
    inventories = PublishedMapInputs().read(plan, guard())
    images(monkeypatch, plan)
    root = Path(plan.files.node_root) / "input"
    expected = {
        str(Path(plan.node_tree(d.role)) / m.file.path): m.mode
        for d, i in zip(plan.trees, inventories, strict=True)
        for m in i.files
    }
    scans: Counter[Path] = Counter()
    synced: list[str] = []
    bytes_read = 0
    counter_lock = threading.Lock()
    inspect = tree_copy.inspect_tree
    original_sync, original_read = os.fsync, os.read
    source_roots = tuple(d.source_root + "/" for d in plan.trees)

    def scan(source: Path, inventory: Any, control: OperationControl) -> Any:
        scans[source] += 1
        return inspect(source, inventory, control)

    def sync(fd: int) -> None:
        path = os.readlink("/proc/self/fd/" + str(fd))
        if path.startswith(str(root) + "/") and stat.S_ISREG(os.fstat(fd).st_mode):
            assert stat.S_IMODE(os.fstat(fd).st_mode) == expected[path]
            synced.append(path)
        original_sync(fd)

    def read(fd: int, count: int) -> bytes:
        nonlocal bytes_read
        raw = original_read(fd, count)
        if os.readlink("/proc/self/fd/" + str(fd)).startswith(source_roots):
            with counter_lock:
                bytes_read += len(raw)
        return raw

    owner = threading.get_ident()
    bounded = guard()

    class OwnerControl:
        def checkpoint(self) -> float:
            assert threading.get_ident() == owner
            return bounded.checkpoint()

        def wait(self, seconds: float) -> None:
            assert threading.get_ident() == owner
            bounded.wait(seconds)

    monkeypatch.setattr(tree_copy, "inspect_tree", scan)
    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "read", read)
    NodeMapInputs().stage(plan, OwnerControl())
    assert scans == Counter({Path(d.source_root): 2 for d in plan.trees})
    assert Counter(synced) == Counter({path: 1 for path in expected})
    assert bytes_read == sum(i.size_bytes for i in inventories)
    assert not any(t.name.startswith("map-file-copy") for t in threading.enumerate())


@pytest.mark.parametrize("fault", ["source", "inventory", "stale"])
def test_preflight_full_binding_and_later_file_change_refused(
    node_path: Path,
    fault: str,
) -> None:
    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    declaration = plan.trees[0]
    checked = tree_copy.check_tree(declaration, inventory, guard())
    if fault == "source":
        declaration = declaration.model_copy(
            update={"source_root": plan.trees[1].source_root}
        )
    elif fault == "inventory":
        first = inventory.files[0]
        inventory = inventory.model_copy(
            update={
                "files": (
                    first.model_copy(update={"mode": first.mode ^ 0o020}),
                    *inventory.files[1:],
                )
            }
        )
    else:
        path = Path(declaration.source_root) / inventory.files[0].file.path
        os.utime(path, ns=(1, 1))
    target = node_path / "clone"
    with pytest.raises(EvidenceIntegrityError, match="Preflight|preflight"):
        tree_copy.clone_tree(declaration, inventory, target, guard(), checked=checked)
    if fault != "stale":
        assert not target.exists()
    else:
        assert target.is_dir() and not (target / inventory.files[0].file.path).exists()


@pytest.mark.parametrize("fault", ["mode", "disk", "sync", "source-change"])
def test_exact_file_mode_io_failure_and_source_change_keep_partial(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    member = inventory.files[0]
    source = Path(plan.trees[0].source_root)
    target = node_path / "copy"
    target.mkdir(mode=0o700)
    original_read = os.read
    failure = OSError("injected " + fault)
    if fault == "disk":

        def write(fd: int, data: Any) -> int:
            raise failure

        monkeypatch.setattr(os, "write", write)
    elif fault == "sync":

        def sync(fd: int) -> None:
            raise failure

        monkeypatch.setattr(os, "fsync", sync)
    elif fault == "source-change":
        changed = False

        def read(fd: int, count: int) -> bytes:
            nonlocal changed
            raw = original_read(fd, count)
            if not changed:
                changed = True
                os.utime(source / member.file.path, ns=(1, 1))
            return raw

        monkeypatch.setattr(os, "read", read)
    with pytest.raises(
        ValueError
        if fault == "mode"
        else EvidenceIntegrityError if fault == "source-change" else OSError
    ) as caught:
        artifact_copy.copy_pinned_file(
            source,
            target,
            member.file,
            guard(),
            final_mode=0o755 if fault == "mode" else member.mode,
        )
    if fault in ["disk", "sync"]:
        assert caught.value is failure
    assert (target / member.file.path).exists() == (fault != "mode")
    if fault == "sync":
        assert stat.S_IMODE((target / member.file.path).stat().st_mode) == member.mode
    if fault != "mode":
        with pytest.raises(FileExistsError):
            artifact_copy.copy_pinned_file(
                source, target, member.file, guard(), final_mode=member.mode
            )


def test_real_stage_hash_failure_never_finalizes_and_stops_writers(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_map_copy_queue import leaves

    plan = runtime_case(node_path)
    inventory = PublishedMapInputs().read(plan, guard())[0]
    path = Path(plan.trees[0].source_root) / inventory.files[0].file.path
    path.write_bytes(b"x" * path.stat().st_size)
    images(monkeypatch, plan)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Failed stage attempted final publication")

    monkeypatch.setattr(stage_module, "finish_clone", forbidden)
    with pytest.raises((EvidenceIntegrityError, BaseExceptionGroup)) as caught:
        NodeMapInputs().stage(plan, guard())
    assert isinstance(leaves(caught.value)[0], EvidenceIntegrityError)
    assert Path(plan.node_tree("app")).is_dir()
    assert not any(t.name.startswith("map-file-copy") for t in threading.enumerate())
    with pytest.raises(FileExistsError):
        NodeMapInputs().stage(plan, guard())


@pytest.mark.parametrize("executable", [False, True])
def test_shared_copier_immutable_default_still_exclusive(
    tmp_path: Path,
    executable: bool,
) -> None:
    import hashlib
    from lab_generate_skill.domain.release import ReleaseFile

    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    raw = b"original shared immutable asset"
    path = source / "asset"
    path.write_bytes(raw)
    path.chmod(0o755 if executable else 0o644)
    entry = ReleaseFile(
        path="asset",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        executable=executable,
    )
    artifact_copy.copy_pinned_file(source, target, entry, guard())
    assert (target / "asset").read_bytes() == raw
    assert stat.S_IMODE((target / "asset").stat().st_mode) == (
        0o555 if executable else 0o444
    )
    with pytest.raises(FileExistsError):
        artifact_copy.copy_pinned_file(source, target, entry, guard())
