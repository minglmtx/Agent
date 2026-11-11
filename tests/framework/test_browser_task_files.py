"""Bounded file delivery, unchanged actions and cancellation/partial-failure exits."""

from collections.abc import Iterator
import os
from pathlib import Path
import tempfile
import pytest
from lab_generate_skill.adapters.browsergym.task_files import LocalBrowserTaskFiles
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_task_files import (
    BrowserTaskFilesPlan,
    upload_paths,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from browser_task_files_fixtures import action, delivery, upload_spec
from test_slurm_commands import guard


@pytest.fixture
def prepared(
    tmp_path: Path,
) -> Iterator[tuple[LocalBrowserTaskFiles, BrowserSessionSpec]]:
    with tempfile.TemporaryDirectory(
        prefix="lab-browser-files-", dir="/tmp"
    ) as directory:
        frozen = upload_spec()
        files = delivery(tmp_path, Path(directory), frozen)
        try:
            yield files, frozen
        finally:
            files.close(guard(5))


@pytest.mark.parametrize(
    "payload",
    [
        "upload_file('7','assets/photo.jpg')",
        "upload_file(file=['assets/other.jpg'],bid='7')",
        "upload_file('7', [])",
    ],
)
def test_native_single_path_alternate_and_clear_are_not_rewritten(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec], payload: str
) -> None:
    files, frozen = prepared
    old = Path.cwd()
    files.prepare(frozen, guard(5))
    original = action(payload)
    files.validate(original, guard(5))
    files.validate(
        original, guard(5)
    )  # pure validation is repeatable; dispatch is one-use in engine
    assert original.payload == payload
    assert Path.cwd() == Path(files.plan.staging_root)
    assert len(upload_paths(original)) <= 1
    with pytest.raises(InvalidTransition):
        files.prepare(frozen, guard(5))
    files.close(guard(5))
    files.close(guard(5))
    assert Path.cwd() == old and Path(files.plan.staging_root).is_dir()


@pytest.mark.parametrize(
    "payload",
    [
        "upload_file('7','/etc/passwd')",
        "upload_file('7','../photo.jpg')",
        "upload_file('7','assets/missing.jpg')",
        "upload_file('7','assets//photo.jpg')",
        "upload_file('7',None)",
        "upload_file('7',True)",
        "upload_file('7',0)",
        "upload_file('7',{})",
        "upload_file('7',('assets/photo.jpg',))",
        "upload_file('7',['assets/photo.jpg','assets/photo.jpg'])",
        "upload_file('7','')",
        "upload_file('7',file_or_list='assets/photo.jpg')",
        "upload_file('7','assets/photo.jpg',file='assets/photo.jpg')",
        "upload_file('7',**{'file':'assets/photo.jpg'})",
        "upload_file('7')",
        "click('7')",
    ],
)
def test_illegal_or_undeclared_upload_has_no_file_effect(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec], payload: str
) -> None:
    files, frozen = prepared
    files.prepare(frozen, guard(5))
    before = {
        p.name: p.read_bytes()
        for p in (Path(files.plan.staging_root) / "assets").iterdir()
    }
    with pytest.raises((ValueError, OwnershipConflict)):
        files.validate(action(payload), guard(5))
    assert before == {
        p.name: p.read_bytes()
        for p in (Path(files.plan.staging_root) / "assets").iterdir()
    }


@pytest.mark.parametrize(
    "kind", ["bytes", "inode", "symlink", "hardlink", "permissions", "cwd"]
)
def test_changed_staged_file_or_directory_refuses_upload(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec], kind: str
) -> None:
    files, frozen = prepared
    files.prepare(frozen, guard(5))
    path = Path(files.plan.staging_root) / "assets/photo.jpg"
    if kind == "bytes":
        path.chmod(0o600)
        path.write_bytes(b"z" * path.stat().st_size)
        path.chmod(0o400)
    elif kind == "inode":
        content = path.read_bytes()
        path.rename(path.with_suffix(".original"))
        path.write_bytes(content)
        path.chmod(0o400)
    elif kind == "symlink":
        path.unlink()
        path.symlink_to("other.jpg")
    elif kind == "hardlink":
        os.link(path, path.with_suffix(".link"))
    elif kind == "permissions":
        path.chmod(0o644)
    else:
        os.chdir(Path(files.plan.staging_root).parent)
    with pytest.raises((EvidenceIntegrityError, OwnershipConflict)):
        files.validate(action(), guard(5))


@pytest.mark.parametrize(
    "kind",
    [
        "wrong-context",
        "no-upload",
        "public-parent",
        "existing-root",
        "source-alias",
        "corrupt-source",
    ],
)
def test_prepare_refuses_wrong_scope_or_unsafe_paths(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec], kind: str
) -> None:
    files, frozen = prepared
    root = Path(files.plan.staging_root)
    if kind == "wrong-context":
        frozen = frozen.model_copy(
            update={"scope": frozen.scope.model_copy(update={"context_id": "wrong"})}
        )
    elif kind == "no-upload":
        frozen = frozen.model_copy(
            update={
                "task": frozen.task.model_copy(update={"allowed_actions": ("click",)})
            }
        )
    elif kind == "public-parent":
        root.parent.chmod(0o755)
    elif kind == "existing-root":
        root.mkdir()
    elif kind == "source-alias":
        source = Path(files.plan.source.root) / "assets/photo.jpg"
        source.unlink()
        source.symlink_to("other.jpg")
    else:
        (Path(files.plan.source.root) / "assets/photo.jpg").write_bytes(b"corrupt")
    old = Path.cwd()
    with pytest.raises((ValueError, EvidenceIntegrityError, FileExistsError)):
        files.prepare(frozen, guard(5))
    assert Path.cwd() == old
    if files.state != "new":
        with pytest.raises(InvalidTransition):
            files.prepare(frozen, guard(5))


def test_partial_copy_is_not_retried_and_cleanup_restores_cwd(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lab_generate_skill.adapters.browsergym.task_files as module

    files, frozen = prepared
    from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file

    original = copy_pinned_file
    count = 0

    def copy(*args: object, **kwargs: object) -> None:
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("second copy failed")
        original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "copy_pinned_file", copy)
    old = Path.cwd()
    with pytest.raises(OSError, match="second copy failed"):
        files.prepare(frozen, guard(5))
    assert count == 2 and (Path(files.plan.staging_root) / "assets/photo.jpg").is_file()
    with pytest.raises(InvalidTransition):
        files.prepare(frozen, guard(5))
    files.close(guard(5))
    assert Path.cwd() == old


def test_one_mib_boundary_and_expired_validation(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix="lab-browser-files-", dir="/tmp"
    ) as directory:
        frozen = upload_spec()
        files = delivery(tmp_path, Path(directory), frozen, 1024**2)
        try:
            files.prepare(frozen, guard(5))
            files.validate(action(), guard(5))

            class Cancelled:
                def checkpoint(self) -> float:
                    raise TimeoutError("cancelled")

                def wait(self, seconds: float) -> None:
                    self.checkpoint()

            with pytest.raises(TimeoutError):
                files.validate(action(), Cancelled())
        finally:
            files.close(guard(5))


@pytest.mark.parametrize(
    "change",
    [
        {"staging_root": "/tmp/browser-uploads"},
        {"staging_root": "/tmp/x/../browser-uploads"},
        {"staging_root": "/var/tmp/x/browser-uploads"},
        {"workspace_root": "/outside"},
        {"workspace_root": None},
        {"staging_root": 7},
    ],
)
def test_invalid_plan_rejected_before_io(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec],
    change: dict[str, object],
) -> None:
    files, _ = prepared
    data = files.plan.model_dump(mode="json")
    data.update(change)
    import json

    with pytest.raises(ValueError):
        BrowserTaskFilesPlan.model_validate_json(json.dumps(data))
    assert not Path(files.plan.staging_root).exists()


def test_engine_keeps_original_payload_and_default_refuses_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
    from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.ports.lifecycle import OperationControl
    from lab_generate_skill.domain.browser import BrowserAction
    from browsergym_fixtures import operation, LoopbackAuthority
    import lab_generate_skill.adapters.browsergym.engine as module

    calls: list[str] = []

    class Files:
        def prepare(self, spec: BrowserSessionSpec, control: OperationControl) -> None:
            calls.append("prepare")

        def validate(self, action: BrowserAction, control: OperationControl) -> None:
            calls.append(action.payload)

        def close(self, control: OperationControl) -> None:
            calls.append("close")

    def step(payload: str) -> None:
        calls.append(payload)
        raise OSError("native return unavailable")

    monkeypatch.setattr(module, "action_set", lambda _: None)
    monkeypatch.setattr(module, "map_action", lambda _a, p, _t: p)
    frozen = upload_spec()
    engine = BrowserGymEngine(
        frozen,
        LoopbackAuthority(),
        SystemClock(),
        NavigatePublicTask(),
        task_files=Files(),
    )
    engine.state = "ready"
    engine.env = SimpleNamespace(step=step)
    original = action()
    with pytest.raises(OSError, match="native return unavailable"):
        engine.step(original, operation(frozen, "upload"), control=guard(5))
    assert (
        calls == [original.payload, original.payload]
        and str(engine.state) == "quarantined"
    )
    engine.close(
        operation(frozen, "initial").cleanup(
            "close", now=SystemClock().utcnow(), seconds=5
        ),
        control=guard(5),
    )
    assert calls[-1] == "close" and str(engine.state) == "closed"
    other = BrowserGymEngine(
        frozen, LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    other.state = "ready"
    other.env = SimpleNamespace(step=step)
    with pytest.raises(OwnershipConflict, match="declared public task files"):
        other.step(original, operation(frozen, "upload"), control=guard(5))
    assert calls == [original.payload, original.payload, "close"]


def test_cancel_after_chdir_restores_original_directory(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files, frozen = prepared
    root = Path(files.plan.staging_root)
    old = Path.cwd()

    class CancelAfterCwd:
        def checkpoint(self) -> float:
            if Path.cwd() == root:
                raise TimeoutError("cancelled after chdir")
            return 5

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError, match="after chdir"):
        files.prepare(frozen, CancelAfterCwd())
    assert Path.cwd() == root and files.state == "quarantined"
    with pytest.raises(InvalidTransition):
        files.prepare(frozen, guard(5))
    files.close(guard(5))
    assert Path.cwd() == old


def test_close_failure_is_quarantined_and_retains_error(
    prepared: tuple[LocalBrowserTaskFiles, BrowserSessionSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lab_generate_skill.adapters.browsergym.task_files as module
    from lab_generate_skill.adapters.releases.artifact_copy import close_all

    files, frozen = prepared
    old = Path.cwd()
    files.prepare(frozen, guard(5))

    def fail_after_close(
        descriptors: tuple[int | None, ...], primary: BaseException | None
    ) -> None:
        close_all(descriptors, primary)
        raise OSError("close acknowledgment lost")

    with monkeypatch.context() as patch:
        patch.setattr(module, "close_all", fail_after_close)
        with pytest.raises(OSError, match="acknowledgment lost"):
            files.close(guard(5))
    assert files.state == "quarantined" and Path.cwd() == old
    assert files.previous is None and files.directory is None
