"""State guard fixtures with real private files and explicitly synthetic SQL."""

import json
from pathlib import Path
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.state_guard import MapStateGuard
from lab_generate_skill.sites.map.state_sql import INSTALL_SQL, STATE_SQL
from map_instance_fixtures import InstanceCase
from test_slurm_commands import guard


class SQL:
    def __init__(self) -> None:
        self.value = dict(
            tables=["notes", "users"],
            tracked=["notes", "users"],
            changed=[],
            sequences=[["notes_id_seq", 1], ["users_id_seq", None]],
        )
        self.calls: list[tuple[tuple[str, ...], bytes]] = []
        self.fail: bytes | None = None
        self.error = OSError("original SQL response unknown")

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        control.checkpoint()
        self.calls.append((argv, data))
        assert data in (INSTALL_SQL.encode(), STATE_SQL.encode())
        if data == self.fail:
            raise self.error
        return (
            b"CREATE SCHEMA\nCREATE TABLE\nCREATE FUNCTION\nDO\n"
            if data == INSTALL_SQL.encode()
            else json.dumps(self.value).encode()
        )


def state_case(case: InstanceCase) -> tuple[MapStateGuard, SQL, Path]:
    case.instance.prepare(guard(60))
    case.instance.start(guard(600))
    root = Path(case.spec.inputs.node_tree("frontend"))
    # The small publication fixture has no native public tree. Model the real
    # directory/files explicitly here, without changing any source publication.
    (root / "public").mkdir(mode=0o700)
    (root / "public/some-asset.js").write_bytes(b"native asset\n")
    (root / "storage/empty").write_bytes(b"")
    sql = SQL()
    state = MapStateGuard(
        case.spec,
        sql,
        NativeMapPersistentFiles(),
        case.group,
        BoundedMapStartupControls(),
    )
    return state, sql, root
