"""Whole prepared instance -> native guard/file proof, no real DB in this gate."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.sites.map.state_guard import MapStateChanged
from lab_generate_skill.sites.map.state_sql import INSTALL_SQL, STATE_SQL
from map_state_fixtures import state_case
from map_instance_fixtures import InstanceCase
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard

ORIGINAL = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/original-capsule/src/lab_generate_skill/map_reset_guard.py"
)


def test_instance_guard_full_files_and_exact_original_capsule_oracle(
    case: InstanceCase,
) -> None:
    tracker, sql, root = state_case(case)
    initial = tracker.install(guard())
    assert initial is tracker.initial and tracker.state == "ready"
    assert [f.path for f in initial.persistent.files] == [
        "storage/empty",
        "public/some-asset.js",
    ]
    assert tracker.require_unchanged(guard()).sha256 == initial.sha256
    assert [raw for _, raw in sql.calls] == [
        INSTALL_SQL.encode(),
        STATE_SQL.encode(),
        STATE_SQL.encode(),
    ]
    for argv, _ in sql.calls:
        assert (
            str(Path(case.spec.inputs.node_tree("app")) / "postgres") + ":/state/pg"
            in argv
        )
        assert argv[-1] == "openstreetmap" and "ON_ERROR_STOP=1" in argv
    # Execute only the pinned original pure guard/oracle with a synthetic SQL
    # provider and original real-file hash reader, never import its runtime.
    nodes = ast.parse(ORIGINAL.read_text()).body
    selected: list[ast.stmt] = [
        n for n in nodes if isinstance(n, (ast.Assign, ast.FunctionDef, ast.ClassDef))
    ]
    namespace: dict[str, Any] = dict(hashlib=hashlib, json=json)
    exec(
        compile(ast.Module(selected, type_ignores=[]), str(ORIGINAL), "exec"), namespace
    )
    assert (
        namespace["INSTALL_SQL"] == INSTALL_SQL and namespace["STATE_SQL"] == STATE_SQL
    )

    class OriginalPath:
        def __truediv__(self, value: str) -> Path:
            assert value == "frontend/app"
            return root

    class OriginalSite:
        state = OriginalPath()
        geographic_baseline = json.loads(initial.persistent.baseline_json)

        def app_sql(self, statement: str) -> str:
            assert statement in (INSTALL_SQL, STATE_SQL)
            return json.dumps(sql.value)

    old = namespace["MapResetGuard"](OriginalSite())
    assert old.initial == initial.sha256
    old.require_unchanged()
    # Empty directories and nonpersistent cache/log files match original scope.
    (root / "storage/empty-dir").mkdir(mode=0o700)
    (root / "tmp/cache-entry").write_bytes(b"transient cache")
    assert tracker.require_unchanged(guard()).sha256 == old.fingerprint()
    with pytest.raises(InvalidTransition):
        tracker.install(guard())
    assert len(case.instance.stop(guard())) == 10


@pytest.mark.parametrize(
    "change", ["table-write", "sequence", "file", "added-file", "removed-file"]
)
def test_changed_original_state_poisoned_without_clearing_or_replay(
    case: InstanceCase, change: str
) -> None:
    tracker, sql, root = state_case(case)
    tracker.install(guard())
    if change == "table-write":
        sql.value["changed"] = ["public.notes"]
    elif change == "sequence":
        sql.value["sequences"] = [["notes_id_seq", 2], ["users_id_seq", None]]
    elif change == "file":
        (root / "public/some-asset.js").write_bytes(b"changed persistent data")
    elif change == "added-file":
        (root / "storage/new").write_bytes(b"changed")
    else:
        (root / "public/some-asset.js").unlink()
    with pytest.raises(MapStateChanged):
        tracker.require_unchanged(guard())
    assert tracker.state == "changed" and len(tracker.observations) == 2
    assert (
        tracker.observations[-1].sha256 != tracker.initial.sha256
        if tracker.initial is not None
        else False
    )
    calls = list(sql.calls)
    with pytest.raises(InvalidTransition):
        tracker.require_unchanged(guard())
    with pytest.raises(InvalidTransition):
        tracker.install(guard())
    assert sql.calls == calls and len(case.instance.stop(guard())) == 10


@pytest.mark.parametrize(
    "phase", ["install", "initial-read", "later-read", "dirty-install"]
)
def test_original_sql_fault_retained_without_retry(
    case: InstanceCase, phase: str
) -> None:
    tracker, sql, root = state_case(case)
    if phase == "later-read":
        tracker.install(guard())
    if phase == "dirty-install":
        sql.value["changed"] = ["public.users"]
    else:
        sql.fail = INSTALL_SQL.encode() if phase == "install" else STATE_SQL.encode()
    operation = tracker.require_unchanged if phase == "later-read" else tracker.install
    with pytest.raises((OSError, MapStateChanged)) as caught:
        operation(guard())
    assert tracker.error is caught.value and tracker.state == "failed"
    calls = list(sql.calls)
    with pytest.raises(InvalidTransition):
        operation(guard())
    assert sql.calls == calls
    assert len(case.instance.stop(guard())) == 10


def test_original_persistent_capture_fault_prevents_ready_or_retry(
    case: InstanceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker, sql, root = state_case(case)
    original = NativeMapPersistentFiles.capture
    error = OSError("capture completed but reply unknown")
    calls = 0

    def fail(self: NativeMapPersistentFiles, spec: Any, control: Any) -> Any:
        nonlocal calls
        calls += 1
        original(self, spec, control)
        raise error

    monkeypatch.setattr(NativeMapPersistentFiles, "capture", fail)
    with pytest.raises(OSError) as caught:
        tracker.install(guard())
    assert (
        caught.value is error and tracker.initial is None and tracker.state == "failed"
    )
    with pytest.raises(InvalidTransition):
        tracker.install(guard())
    assert calls == 1 and len(case.instance.stop(guard())) == 10


def test_guard_cancellation_after_install_sql_never_reinstalls(
    case: InstanceCase,
) -> None:
    tracker, sql, root = state_case(case)

    class Stop:
        def checkpoint(self) -> float:
            if sql.calls:
                raise TimeoutError("cancelled after guard schema installation")
            return 60.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        tracker.install(Stop())
    assert [data for _, data in sql.calls] == [INSTALL_SQL.encode()]
    assert tracker.initial is None and tracker.state == "failed"
    with pytest.raises(InvalidTransition):
        tracker.install(guard())
    assert len(case.instance.stop(guard())) == 10


def test_foreign_guard_owner_has_no_sql_or_file_capture(case: InstanceCase) -> None:
    tracker, sql, root = state_case(case)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(tracker.install, guard()).result()
    assert tracker.state == "new" and not sql.calls
    with pytest.raises(InvalidTransition):
        tracker.require_unchanged(guard())
    assert len(case.instance.stop(guard())) == 10
