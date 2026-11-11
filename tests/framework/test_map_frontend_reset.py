"""Original full guard -> Rails retirement/clear -> replacement/health/guard."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.map_frontend_lifecycle import MapFrontendCleared
from lab_generate_skill.adapters.map_runtime import frontend_transients as native
from lab_generate_skill.adapters.map_runtime.frontend_transients import (
    NativeMapFrontendTransients,
)
from lab_generate_skill.sites.map.state_guard import MapStateChanged
from map_frontend_reset_fixtures import reset_case
from map_service_generations_fixtures import GenerationCase
from test_map_service_generations import generations
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def tree(root: Path) -> list[tuple[str, str]]:
    return [
        (
            str(p.relative_to(root)),
            (
                "link:" + os.readlink(p)
                if p.is_symlink()
                else (
                    "directory"
                    if p.is_dir()
                    else hashlib.sha256(p.read_bytes()).hexdigest()
                )
            ),
        )
        for p in sorted(root.rglob("*"))
    ]


@pytest.mark.parametrize("forced", [False, True])
def test_full_original_guard_retire_clear_resume_combination_and_capsule_parity(
    generations: GenerationCase, forced: bool
) -> None:
    reset, sql, root = reset_case(generations)
    initial = reset.guard.initial
    assert initial is not None
    expected = root.with_name("original-clear-oracle")
    shutil.copytree(root, expected)
    source = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/original-capsule/src/lab_generate_skill/map_query_site.py"
    )
    nodes: list[ast.stmt] = [
        n
        for n in ast.parse(source.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "clear_frontend_transients"
    ]
    assert len(nodes) == 1
    namespace: dict[str, Any] = dict(Path=Path, shutil=shutil)
    exec(compile(ast.Module(nodes, type_ignores=[]), str(source), "exec"), namespace)
    namespace["clear_frontend_transients"](expected, preserve_compiled_assets=True)
    if forced:
        generations.force()
    cleared = reset.begin(guard())
    assert reset.state == "retired" and reset.stopped is not None
    assert reset.stopped.forced_namespace is forced
    assert tree(root) == tree(expected)
    assert cleared.preserved_sprockets and cleared.preserve_compiled_assets
    assert set(cleared.removed) == {
        "tmp/cache/assets/other",
        "tmp/cache/session",
        "tmp/pids",
    }
    marker = Path(reset.spec.inputs.files.node_root) / "frontend-reset-1"
    assert (
        MapFrontendCleared.model_validate_json((marker / "cleared.json").read_bytes())
        == cleared
    )
    with pytest.raises(InvalidTransition):
        reset.begin(guard())
    with pytest.raises(FileExistsError):
        NativeMapFrontendTransients().clear(reset.spec, reset.stopped, guard())
    result = reset.resume(guard(600))
    assert reset.state == "resumed" and result.endpoint == reset.spec.endpoint
    assert result.before_sha256 == result.after_sha256 == initial.sha256
    assert len(reset.guard.observations) == 3 and reset.frontend == result.frontend
    assert len(generations.groups) == 11 and tree(root) == tree(expected)
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 11
    assert generations.case.ports.lease.releases == 0


@pytest.mark.parametrize("phase", ["before", "after"])
def test_dirty_original_state_never_becomes_safe_reset_or_replays(
    generations: GenerationCase, phase: str
) -> None:
    reset, sql, root = reset_case(generations)
    if phase == "after":
        reset.begin(guard())
    sql.value["changed"] = ["public.users"]
    operation = reset.begin if phase == "before" else reset.resume
    with pytest.raises(MapStateChanged):
        operation(guard())
    assert reset.state == "failed" and reset.guard.state == "changed"
    calls = list(sql.calls)
    with pytest.raises(InvalidTransition):
        operation(guard())
    assert sql.calls == calls
    if phase == "before":
        assert reset.stopped is None and not generations.rails().quiet_calls
        assert (root / "tmp/cache/session").exists()
    else:
        assert reset.frontend is not None and reset.result is None
    assert len(generations.instance.stop(guard())) == (10 if phase == "before" else 11)


@pytest.mark.parametrize("change", ["cache-alias", "pid-hardlink", "tmp-alias"])
def test_invalid_transient_scope_after_stop_is_isolated_without_mutation(
    generations: GenerationCase, change: str
) -> None:
    reset, sql, root = reset_case(generations)
    if change == "cache-alias":
        target = root / "saved-cache"
        (root / "tmp/cache").rename(target)
        (root / "tmp/cache").symlink_to(target, target_is_directory=True)
    elif change == "pid-hardlink":
        os.link(root / "tmp/pids/nested/puma.pid", root / "tmp/linked-pid")
    else:
        target = root / "saved-tmp"
        (root / "tmp").rename(target)
        (root / "tmp").symlink_to(target, target_is_directory=True)
    before = tree(root)
    with pytest.raises(EvidenceIntegrityError):
        reset.begin(guard())
    assert (
        reset.state == "failed" and reset.stopped is not None and reset.cleared is None
    )
    assert tree(root) == before
    assert not (Path(reset.spec.inputs.files.node_root) / "frontend-reset-1").exists()
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 10


def test_native_pid_and_cache_symlinks_unlinked_without_touching_targets(
    generations: GenerationCase,
) -> None:
    reset, sql, root = reset_case(generations)
    target = root / "tmp/other-file"
    shutil.rmtree(root / "tmp/pids")
    (root / "tmp/pids").symlink_to(target)
    (root / "tmp/cache/link").symlink_to(target)
    reset.begin(guard())
    assert target.read_bytes() == b"original other temporary file"
    assert (root / "tmp/pids").is_dir() and not (root / "tmp/pids").is_symlink()
    assert not os.path.lexists(root / "tmp/cache/link")
    reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 11


def test_absent_cache_and_pids_created_without_persistent_change(
    generations: GenerationCase,
) -> None:
    reset, sql, root = reset_case(generations)
    shutil.rmtree(root / "tmp/cache")
    shutil.rmtree(root / "tmp/pids")
    result = reset.begin(guard())
    assert result.removed == () and not result.preserved_sprockets
    assert not list((root / "tmp/cache").iterdir()) and not list(
        (root / "tmp/pids").iterdir()
    )
    reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 11


def test_partial_delete_reply_unknown_retains_marker_and_original_stop(
    generations: GenerationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset, sql, root = reset_case(generations)
    original = Path.unlink
    calls = 0
    error = OSError("original unlink committed, confirmation lost")

    def fail(path: Path, *args: Any, **kwargs: Any) -> None:
        nonlocal calls
        original(path, *args, **kwargs)
        calls += 1
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail)
        with pytest.raises(OSError) as caught:
            reset.begin(guard())
    assert caught.value is error and calls == 1 and reset.state == "failed"
    assert reset.stopped is not None and reset.cleared is None
    marker = Path(reset.spec.inputs.files.node_root) / "frontend-reset-1"
    assert (marker / "intent.json").exists() and not (marker / "cleared.json").exists()
    with pytest.raises(FileExistsError):
        NativeMapFrontendTransients().clear(reset.spec, reset.stopped, guard())
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 10


def test_cancel_after_reservation_clears_nothing_and_does_not_resume(
    generations: GenerationCase,
) -> None:
    reset, sql, root = reset_case(generations)
    before = tree(root)
    marker = Path(reset.spec.inputs.files.node_root) / "frontend-reset-1"

    class Stop:
        def checkpoint(self) -> float:
            if marker.exists():
                raise TimeoutError("cancelled after original clear reservation")
            return 60.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        reset.begin(Stop())
    assert marker.exists() and tree(root) == before and reset.state == "failed"
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 10


def test_cleared_receipt_committed_but_reply_unknown_never_repeats(
    generations: GenerationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset, sql, root = reset_case(generations)
    from lab_generate_skill.adapters.map_artifacts.files import write_once

    original = write_once
    error = OSError("original cleared receipt confirmation lost")

    def fail(
        directory: Path, name: str, data: bytes, control: Any, *, readonly: bool = False
    ) -> Any:
        result = original(directory, name, data, control, readonly=readonly)
        if name == "cleared.json":
            raise error
        return result

    monkeypatch.setattr(native, "write_once", fail)
    with pytest.raises(OSError) as caught:
        reset.begin(guard())
    assert caught.value is error and reset.cleared is None and reset.stopped is not None
    assert (
        Path(reset.spec.inputs.files.node_root) / "frontend-reset-1/cleared.json"
    ).exists()
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    with pytest.raises(FileExistsError):
        NativeMapFrontendTransients().clear(reset.spec, reset.stopped, guard())
    assert len(generations.instance.stop(guard())) == 10


def test_failed_replacement_health_retains_new_generation_without_post_guard(
    generations: GenerationCase,
) -> None:
    reset, sql, root = reset_case(generations)
    reset.begin(guard())
    generations.case.commands.http = [b'{"status":500,"body_base64":"ZXJyb3I="}']
    calls = len(sql.calls)
    with pytest.raises(ValueError, match="did not complete with 200"):
        reset.resume(guard())
    assert reset.state == "failed" and reset.frontend is None and reset.after is None
    assert len(sql.calls) == calls and len(generations.groups) == 11
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 11


@pytest.mark.parametrize("action", ["begin", "resume"])
def test_foreign_owner_or_unprepared_resume_never_effects(
    generations: GenerationCase, action: str
) -> None:
    reset, sql, root = reset_case(generations)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(getattr(reset, action), guard()).result()
    assert reset.state == "new" and not generations.rails().quiet_calls
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 10


def test_clear_receipt_scope_and_wrong_generation_never_allow_resume(
    generations: GenerationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset, sql, root = reset_case(generations)
    original = reset.files.clear

    def wrong(spec: Any, stopped: Any, control: Any) -> MapFrontendCleared:
        result = original(spec, stopped, control)
        data = result.model_dump()
        for paths in [
            ("public/original",),
            ("tmp/other-file",),
            ("tmp/cache/session", "tmp/cache/session"),
            ("tmp/cache/../public",),
            ("tmp/cache/assets/sprockets",),
        ]:
            with pytest.raises(ValueError):
                MapFrontendCleared.model_validate({**data, "removed": paths})
        with pytest.raises(ValueError):
            MapFrontendCleared.model_validate({**data, "removed": []})
        return MapFrontendCleared.model_validate(
            {**data, "stopped": {**data["stopped"], "generation": 2}}
        )

    monkeypatch.setattr(reset.files, "clear", wrong)
    with pytest.raises(OwnershipConflict):
        reset.begin(guard())
    assert reset.cleared is not None and reset.cleared.stopped.generation == 2
    assert reset.stopped is not None and reset.stopped.generation == 1
    with pytest.raises(InvalidTransition):
        reset.resume(guard())
    assert len(generations.instance.stop(guard())) == 10
