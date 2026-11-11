"""Whole small Map instance/state guard and real frontend cache/PID fixture."""

from pathlib import Path
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.adapters.map_runtime.frontend_transients import (
    NativeMapFrontendTransients,
)
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.sites.map.state_guard import MapStateGuard
from lab_generate_skill.sites.map.frontend_reset import MapFrontendReset
from map_service_generations_fixtures import GenerationCase
from map_state_fixtures import SQL
from test_slurm_commands import guard


def reset_case(case: GenerationCase) -> tuple[MapFrontendReset, SQL, Path]:
    owned = case.owned
    assert owned is not None
    spec = case.case.spec
    root = Path(spec.inputs.node_tree("frontend"))
    (root / "public").mkdir(mode=0o700)
    for name, body in {
        "public/original": b"persistent public file",
        "storage/original": b"persistent storage file",
        "tmp/cache/assets/sprockets/compiled.js": b"same deployment compiled bytes",
        "tmp/cache/assets/other/unrelated": b"old cache",
        "tmp/cache/session": b"old session",
        "tmp/pids/nested/puma.pid": b"1234",
        "tmp/other-file": b"original other temporary file",
        "log/original": b"original log",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    # Real Rails may use 0755 descendants inside its private 0700 tmp ancestor.
    (root / "tmp/cache").chmod(0o755)
    sql = SQL()
    tracker = MapStateGuard(
        spec, sql, NativeMapPersistentFiles(), owned, BoundedMapStartupControls()
    )
    tracker.install(guard())
    reset = MapFrontendReset(
        spec,
        tracker,
        owned,
        NativeMapFrontendTransients(),
        case.case.commands,
        BoundedMapStartupControls(),
    )
    return reset, sql, root
