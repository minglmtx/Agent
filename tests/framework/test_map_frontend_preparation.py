"""Real node frontend rewrite, complete original retention and service composition."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.domain.map_frontend import MapFrontendPrepared
from lab_generate_skill.adapters.map_runtime import frontend as native
from lab_generate_skill.sites.map.frontend_sources import preparation
from map_frontend_fixtures import frontend_case, originals, prepared_generation
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_complete_private_changes_originals_receipt_and_no_repeat(
    node_path: Path,
) -> None:
    spec, files, frontend = frontend_case(node_path)
    source = originals()
    plan = preparation(spec, files.read(spec, guard()))
    result = frontend.prepare(guard())
    assert result == frontend.receipt and frontend.state == "prepared"
    result.check(plan)
    root, marker = Path(spec.inputs.node_tree("frontend")), Path(plan.marker)
    saved = MapFrontendPrepared.model_validate_json(
        (marker / "prepared.json").read_bytes()
    )
    assert saved == result
    for index, pin in enumerate(plan.original):
        assert (marker / f"original-{index:02d}").read_bytes() == source[pin.path]
    changed = {p.path: p for p in result.changed}
    for pin in result.original:
        expected = changed.get(pin.path, pin)
        assert (
            hashlib.sha256((root / pin.path).read_bytes()).hexdigest()
            == expected.sha256
        )
        assert (root / pin.path).stat().st_mode & 0o777 == 0o600
    original_root = Path(
        next(t.source_root for t in spec.inputs.trees if t.role == "frontend")
    )
    for name, body in source.items():
        assert (original_root / name).read_bytes() == body
    for name in ("log", "tmp", "storage"):
        assert not list((root / name).iterdir())
    assert not (root / "node_modules").exists()
    with pytest.raises(InvalidTransition):
        frontend.prepare(guard())
    with pytest.raises(FileExistsError):
        files.apply(plan, guard())


def test_frontend_preparation_then_original_ten_service_combination(
    node_path: Path,
) -> None:
    with prepared_generation(node_path) as (frontend, generation, commands, group):
        assert frontend.state == "prepared"
        assert generation.start(guard(600)) == generation.spec.endpoint
        assert len(group.pins) == 10 and len(generation.stop(guard())) == 10
        assert frontend.receipt is not None and len(frontend.receipt.changed) == 7


@pytest.mark.parametrize(
    "change", ["drift", "symlink", "hardlink", "transient", "missing"]
)
def test_wrong_original_clone_prevents_mutation(node_path: Path, change: str) -> None:
    spec, files, frontend = frontend_case(node_path)
    plan = preparation(spec, files.read(spec, guard()))
    root = Path(spec.inputs.node_tree("frontend"))
    path = root / "app/controllers/api/map_controller.rb"
    if change == "drift":
        path.write_bytes(path.read_bytes() + b"x")
    elif change == "symlink":
        target = path.with_suffix(".saved")
        path.rename(target)
        path.symlink_to(target)
    elif change == "hardlink":
        os.link(path, root / "extra-hardlink")
    elif change == "transient":
        (root / "log").mkdir()
    else:
        path.unlink()
    with pytest.raises((EvidenceIntegrityError, FileNotFoundError)):
        files.apply(plan, guard())
    assert not Path(plan.marker).exists()


def test_partial_replace_unknown_preserves_originals_and_never_rewrites(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, files, frontend = frontend_case(node_path)
    plan = preparation(spec, files.read(spec, guard()))
    replace = os.replace
    calls = 0
    error = OSError("original replace reply unknown")

    def fail(source: Any, target: Any) -> None:
        nonlocal calls
        calls += 1
        replace(source, target)
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail)
        with pytest.raises(OSError) as caught:
            frontend.prepare(guard())
    assert caught.value is error and calls == 1 and frontend.state == "failed"
    marker = Path(plan.marker)
    assert (
        len(list(marker.glob("original-*"))) == 14
        and not (marker / "prepared.json").exists()
    )
    first = plan.changes[0]
    assert (
        Path(spec.inputs.node_tree("frontend")) / first.original.path
    ).read_bytes() == first.content
    with pytest.raises(InvalidTransition):
        frontend.prepare(guard())
    with pytest.raises(FileExistsError):
        files.apply(plan, guard())


def test_cancel_after_reservation_retains_marker_and_original_source(
    node_path: Path,
) -> None:
    spec, files, frontend = frontend_case(node_path)
    plan = preparation(spec, files.read(spec, guard()))

    class Stop:
        def checkpoint(self) -> float:
            if Path(plan.marker).exists():
                raise TimeoutError("original frontend preparation cancelled")
            return 20.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        frontend.prepare(Stop())
    assert Path(plan.marker).is_dir() and frontend.state == "failed"
    for name, raw in originals().items():
        assert (Path(spec.inputs.node_tree("frontend")) / name).read_bytes() == raw
    with pytest.raises(FileExistsError):
        files.apply(plan, guard())


def test_receipt_write_unknown_is_not_prepared_or_replayed(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, files, frontend = frontend_case(node_path)
    plan = preparation(spec, files.read(spec, guard()))
    from lab_generate_skill.adapters.map_artifacts.files import write_once

    error = OSError("original prepared receipt confirmation lost")

    def fail(
        root: Path, name: str, data: bytes, control: Any, *, readonly: bool = False
    ) -> Any:
        result = write_once(root, name, data, control, readonly=readonly)
        if name == "prepared.json":
            raise error
        return result

    monkeypatch.setattr(native, "write_once", fail)
    with pytest.raises(OSError) as caught:
        frontend.prepare(guard())
    assert (
        caught.value is error
        and frontend.state == "failed"
        and frontend.receipt is None
    )
    assert (Path(plan.marker) / "prepared.json").exists()
    with pytest.raises(InvalidTransition):
        frontend.prepare(guard())
    with pytest.raises(FileExistsError):
        files.apply(plan, guard())


def test_original_write_and_close_errors_both_retained(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, files, frontend = frontend_case(node_path)
    close = os.close
    failed = False
    original, cleanup = OSError("original intent write failed"), OSError(
        "original close failed"
    )

    def fail_write(fd: int, data: Any) -> int:
        nonlocal failed
        failed = True
        raise original

    def fail_close(fd: int) -> None:
        close(fd)
        if failed:
            raise cleanup

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", fail_write)
        patch.setattr(os, "close", fail_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            frontend.prepare(guard())
    assert caught.value.exceptions == (original, cleanup) and frontend.state == "failed"


def test_foreign_owner_has_no_file_effect(node_path: Path) -> None:
    spec, files, frontend = frontend_case(node_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(frontend.prepare, guard()).result()
    assert (
        frontend.state == "new"
        and not (Path(spec.inputs.files.node_root) / "frontend-preparation").exists()
    )


def test_reservation_parent_sync_failure_never_changes_source(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, files, frontend = frontend_case(node_path)
    root = Path(spec.inputs.files.node_root)
    from lab_generate_skill.adapters.releases.artifact_copy import sync_directory

    calls: list[Path] = []
    error = OSError("original reservation directory sync failed")

    def fail(path: Path) -> None:
        calls.append(path)
        if path == root:
            raise error
        sync_directory(path)

    monkeypatch.setattr(native, "sync_directory", fail)
    with pytest.raises(OSError) as caught:
        frontend.prepare(guard())
    assert caught.value is error and calls == [root] and frontend.state == "failed"
    marker = root / "frontend-preparation"
    assert marker.is_dir() and not list(marker.iterdir())
    for name, raw in originals().items():
        assert (Path(spec.inputs.node_tree("frontend")) / name).read_bytes() == raw
    with pytest.raises(InvalidTransition):
        frontend.prepare(guard())
