"""Original search identity, bounded commands and failure ownership; no live server."""

import json
from pathlib import Path
from typing import Any, Literal
from collections.abc import Callable
import pytest
from pydantic import ValidationError
from lab_generate_skill.sites.shopping_admin.search import AdminSearch
from lab_generate_skill.sites.shopping_admin.search_contract import AdminSearchSnapshot
from lab_generate_skill.sites.shopping_admin.search_authority import (
    AdminSearchAuthority,
)
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.search_program import SEARCH_SNAPSHOT_PHP
from lab_generate_skill.ports.lifecycle import OperationControl
from test_admin_services import spec
from test_slurm_commands import guard


class Authority:
    def __init__(self) -> None:
        self.denied = False
        self.phases: list[str] = []

    def verify(
        self,
        service: AdminServiceSpec,
        phase: Literal["save", "verify", "preflight", "restore"],
        snapshot: AdminSearchSnapshot | None,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.phases.append(phase)
        if self.denied:
            raise PermissionError("search denied")
        assert (snapshot is None) == (phase == "save")


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.change: dict[str, Any] = {}
        self.error: BaseException | None = None
        self.after: Callable[[], None] | None = None
        self.indices: list[str] = ["catalog_product_1_v1"]
        self.raw: bytes | None = None

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        if self.error:
            raise self.error
        phase = argv[-2]
        value: dict[str, Any] = dict(
            schema_version="admin-search-reply/2",
            operation=phase,
            snapshot=dict(
                cluster_uuid="original-cluster",
                version="7.10.1",
                repository="lab_admin_recovery",
                snapshot="baseline",
                snapshot_uuid="original-snapshot",
                indices=self.indices,
                data_streams=[],
                shards=len(self.indices),
            ),
        )
        if phase == "restore":
            value.update(health="yellow", successful_shards=len(self.indices))
        value.update(self.change)
        if self.after:
            self.after()
        return (
            self.raw
            if self.raw is not None
            else json.dumps(value, separators=(",", ":")).encode()
        )


def case(root: Path) -> tuple[AdminSearch, Commands, Authority]:
    commands, authority = Commands(), Authority()
    return AdminSearch(spec(root), commands, authority), commands, authority


@pytest.mark.parametrize("empty", [False, True])
def test_save_readonly_verify_restore_original_and_repeat_guards(
    tmp_path: Path, empty: bool
) -> None:
    worker, commands, authority = case(tmp_path)
    if empty:
        commands.indices = []
    saved = worker.save(guard())
    worker.verify(saved, guard())
    worker.verify(saved, guard())
    restored = worker.restore(saved, guard())
    assert restored.original == saved and restored.restored_indices == saved.indices
    assert authority.phases == ["save", "verify", "verify", "restore"]
    calls = len(commands.calls)
    with pytest.raises(RuntimeError):
        worker.save(guard())
    with pytest.raises(RuntimeError):
        worker.restore(saved, guard())
    assert len(commands.calls) == calls
    for argv in commands.calls:
        assert SEARCH_SNAPSHOT_PHP in argv and argv[-4] == str(
            worker.service.ports.search
        )
        assert float(argv[-3]) > 0 and "http" not in argv[-1]


@pytest.mark.parametrize("mode", ["save", "verify", "restore"])
def test_permission_before_native_effect(tmp_path: Path, mode: str) -> None:
    worker, commands, authority = case(tmp_path)
    saved = worker.save(guard())
    calls = len(commands.calls)
    if mode == "save":
        worker = AdminSearch(worker.service, commands, authority)
    authority.denied = True
    with pytest.raises(PermissionError):
        if mode == "save":
            worker.save(guard())
        elif mode == "verify":
            worker.verify(saved, guard())
        else:
            worker.restore(saved, guard())
    assert len(commands.calls) == calls and not worker.busy and not worker.quarantined


@pytest.mark.parametrize("mode", ["save", "verify", "restore"])
def test_original_error_keeps_phase_and_snapshot_no_retry(
    tmp_path: Path, mode: str
) -> None:
    worker, commands, _ = case(tmp_path)
    saved = None
    if mode != "save":
        saved = worker.save(guard())
    error = OSError("native fault")
    commands.error = error
    with pytest.raises(OSError) as caught:
        if mode == "save":
            worker.save(guard())
        elif mode == "verify":
            assert saved is not None
            worker.verify(saved, guard())
        else:
            assert saved is not None
            worker.restore(saved, guard())
    assert caught.value is error and getattr(error, "admin_search_phase") == mode
    assert (
        getattr(error, "admin_search_snapshot") == saved
        and worker.quarantined
        and not worker.busy
    )
    calls = len(commands.calls)
    with pytest.raises(RuntimeError):
        worker.save(guard())
    assert len(commands.calls) == calls


@pytest.mark.parametrize(
    "change",
    [
        "service",
        "cluster",
        "uuid",
        "indices",
        "data_streams",
        "shards",
        "version",
        "repository",
    ],
)
def test_original_snapshot_identity_cannot_change(tmp_path: Path, change: str) -> None:
    worker, commands, _ = case(tmp_path)
    saved = worker.save(guard())
    values: dict[str, Any] = {
        "service": saved.service.model_copy(
            update={"ports": saved.service.ports.model_copy(update={"search": 13004})}
        ),
        "cluster": "other",
        "uuid": "other",
        "indices": ("other-index",),
        "data_streams": ("events",),
        "shards": 2,
        "version": "7.10.2",
        "repository": "other",
    }
    fields = {"cluster": "cluster_uuid", "uuid": "snapshot_uuid"}
    changed = saved.model_copy(update={fields.get(change, change): values[change]})
    with pytest.raises((ValueError, ValidationError)):
        worker.restore(changed, guard())
    assert (
        all(c[-2] != "restore" for c in commands.calls)
        if change in ("service", "repository")
        else worker.quarantined
    )


@pytest.mark.parametrize("bad", [None, {}, [], "", 1])
def test_bad_snapshot_rejected_before_call(tmp_path: Path, bad: Any) -> None:
    worker, commands, _ = case(tmp_path)
    with pytest.raises(ValidationError):
        worker.verify(bad, guard())
    assert not commands.calls


@pytest.mark.parametrize(
    "names",
    [("*",), ("a,b",), ("../x",), ("_all",), ("a", "a"), ("b", "a"), (".",), ("A",)],
)
@pytest.mark.parametrize("field", ["indices", "data_streams"])
def test_literal_index_names_only(
    tmp_path: Path, names: tuple[str, ...], field: str
) -> None:
    worker, _, _ = case(tmp_path)
    saved = worker.save(guard())
    with pytest.raises(ValidationError):
        AdminSearchSnapshot.model_validate(saved.model_copy(update={field: names}))


@pytest.mark.parametrize("bad", [True, -1, "1", None])
def test_shards_exact_type(tmp_path: Path, bad: Any) -> None:
    worker, _, _ = case(tmp_path)
    saved = worker.save(guard())
    with pytest.raises(ValidationError):
        AdminSearchSnapshot.model_validate(saved.model_copy(update={"shards": bad}))


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "verify"},
        {"health": "green"},
        {"successful_shards": True},
        {"unknown": "field"},
    ],
)
def test_bad_reply_quarantines_and_preserves_original(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    worker, commands, _ = case(tmp_path)
    commands.change = change
    with pytest.raises((ValueError, ValidationError)):
        worker.save(guard())
    assert worker.quarantined and not worker.busy


@pytest.mark.parametrize("raw", [b"", b"null", b"[]", b"{bad", b"{}"])
def test_invalid_native_json(tmp_path: Path, raw: bytes) -> None:
    worker, commands, _ = case(tmp_path)
    commands.raw = raw
    with pytest.raises(ValidationError):
        worker.save(guard())
    assert worker.quarantined


def test_final_cancellation_preserves_saved_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, commands, _ = case(tmp_path)
    control = guard()

    def stopped() -> float:
        raise OSError("stop after native reply")

    commands.after = lambda: monkeypatch.setattr(control, "checkpoint", stopped)
    with pytest.raises(OSError) as e:
        worker.save(control)
    assert (
        worker.saved is not None
        and getattr(e.value, "admin_search_snapshot") == worker.saved
    )
    assert worker.quarantined and not worker.busy


def test_reentrancy_has_no_second_command(tmp_path: Path) -> None:
    worker, commands, _ = case(tmp_path)

    def nested() -> None:
        with pytest.raises(RuntimeError):
            worker.save(guard())

    commands.after = nested
    worker.save(guard())
    assert len(commands.calls) == 1


@pytest.mark.parametrize("count", [0, 256, 257])
def test_inventory_size_bound(tmp_path: Path, count: int) -> None:
    worker, _, _ = case(tmp_path)
    saved = worker.save(guard())
    data = saved.model_dump()
    data["indices"] = tuple(f"index-{i:03d}" for i in range(count))
    if count <= 256:
        assert len(AdminSearchSnapshot.model_validate(data).indices) == count
    else:
        with pytest.raises(ValidationError):
            AdminSearchSnapshot.model_validate(data)


@pytest.mark.parametrize("mode", ["preflight", "old_reply"])
def test_preflight_and_old_reply_contract(tmp_path: Path, mode: str) -> None:
    worker, commands, authority = case(tmp_path)
    saved = worker.save(guard())
    if mode == "old_reply":
        commands.change["schema_version"] = "admin-search-reply/1"
        with pytest.raises(ValueError):
            worker.preflight_restore(saved, guard())
        assert worker.quarantined
    else:
        worker.preflight_restore(saved, guard())
        worker.preflight_restore(saved, guard())
        assert authority.phases == ["save", "preflight", "preflight"]
        assert not worker.restore_attempted
