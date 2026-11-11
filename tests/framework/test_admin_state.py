"""Composed preflight, precise failures and private cache scope with actual files."""

from pathlib import Path
from typing import Any, Literal
import pytest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.state import AdminState
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.state_contract import (
    AdminStatePlan,
    AdminStateSnapshot,
)
from lab_generate_skill.sites.shopping_admin.database_contract import DatabaseReply
from lab_generate_skill.sites.shopping_admin.artifact_contract import (
    AdminArtifactLayout,
)
from lab_generate_skill.sites.shopping_admin.caches import AdminCaches
from test_admin_services import spec
from test_slurm_commands import guard
from test_admin_search import Commands as SearchCommands, Authority as SearchAuthority
from lab_generate_skill.sites.shopping_admin.search_program import SEARCH_SNAPSHOT_PHP


def command_phase(argv: tuple[str, ...]) -> str:
    if SEARCH_SNAPSHOT_PHP in argv:
        return "search:" + argv[-2]
    return (
        argv[-1]
        if argv[-1] in ("save", "FLUSHALL", "keyspace", "cache:flush")
        else argv[-3]
    )


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail: str | None = None
        self.search_commands = SearchCommands()
        self.flush = b"OK\n"
        self.keyspace = b"# Keyspace\r\n\r\n"

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        mode = command_phase(argv)
        if mode == self.fail:
            raise OSError("failed-" + mode)
        if mode.startswith("search:"):
            return self.search_commands.run(argv, control)
        if mode in ("save", "verify", "restore"):
            return DatabaseReply(operation=mode, size_bytes=123, sha256="a" * 64).model_dump_json().encode()  # type: ignore[arg-type]
        if mode == "FLUSHALL":
            return self.flush
        if mode == "keyspace":
            return self.keyspace
        if mode == "cache:flush":
            return b"application flushed"
        raise AssertionError(argv)


class Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.deny = False

    def verify(
        self,
        plan: AdminStatePlan,
        phase: Literal["save", "restore"],
        snapshot: AdminStateSnapshot | None,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(phase)
        if self.deny:
            raise PermissionError("no original scope")


def state(
    root: Path, *, service: AdminServiceSpec | None = None
) -> tuple[AdminState, Commands, Authority]:
    service = spec(root) if service is None else service
    app = root / "state/app"
    (app / "var/training-mail").mkdir(parents=True)
    (app / "var/training-mail/message").write_bytes(b"original")
    plan = AdminStatePlan(
        service=service,
        artifacts=AdminArtifactLayout(
            instance_id=service.layout.instance_id,
            node_root=str(root),
            app_root=str(app),
            backup_root=str(root / "backup"),
            paths=("var/training-mail", "pub/media/training-assets"),
        ),
    )
    commands = Commands()
    authority = Authority()
    return AdminState(plan, commands, authority, SearchAuthority()), commands, authority


def mutate(worker: AdminState) -> Path:
    path = Path(worker.plan.artifacts.app_root) / "var/training-mail/message"
    path.write_bytes(b"changed")
    return path


def test_save_restore_exact_plan_all_preflight_before_mutation_and_repeat(
    tmp_path: Path,
) -> None:
    worker, commands, authority = state(tmp_path)
    saved = worker.save(guard())
    path = mutate(worker)
    returned = worker.restore(
        AdminStateSnapshot.model_validate_json(saved.model_dump_json()), guard()
    )
    assert (
        returned.snapshot_sha256 == saved.digest
        and returned.database.operation == "restore"
    )
    assert (
        returned.artifacts == saved.artifacts
        and returned.cache.redis_all_databases_empty
    )
    assert path.read_bytes() == b"original"
    assert returned.search.original == saved.search
    assert [command_phase(v) for v in commands.calls] == [
        "search:save",
        "save",
        "verify",
        "search:preflight",
        "restore",
        "cache:flush",
        "FLUSHALL",
        "keyspace",
        "search:restore",
    ]
    count = len(commands.calls)
    with pytest.raises(RuntimeError, match="already attempted"):
        worker.restore(saved, guard())
    assert len(commands.calls) == count
    with pytest.raises(RuntimeError):
        worker.save(guard())
    assert authority.calls == ["save", "restore"]


@pytest.mark.parametrize("failure", ["database", "artifact", "search", "wrong_plan"])
def test_all_snapshots_preflight_before_database_restore(
    tmp_path: Path, failure: str
) -> None:
    worker, commands, _ = state(tmp_path)
    saved = worker.save(guard())
    path = mutate(worker)
    if failure == "database":
        commands.fail = "verify"
    elif failure == "search":
        commands.fail = "search:preflight"
    elif failure == "artifact":
        (worker.artifacts.backup / "0/message").write_bytes(b"bad")
    else:
        saved = saved.model_copy(
            update={
                "plan": saved.plan.model_copy(
                    update={
                        "service": saved.plan.service.model_copy(
                            update={
                                "ports": saved.plan.service.ports.model_copy(
                                    update={"redis": 13003}
                                )
                            }
                        )
                    }
                )
            }
        )
    with pytest.raises((OSError, ValueError)):
        worker.restore(saved, guard())
    assert not any("restore" == v[-3] for v in commands.calls if len(v) > 3)
    assert path.read_bytes() == b"changed"


@pytest.mark.parametrize(
    "phase", ["restore", "cache:flush", "FLUSHALL", "keyspace", "search:restore"]
)
def test_partial_failure_retains_snapshot_progress_and_quarantines(
    tmp_path: Path, phase: str
) -> None:
    worker, commands, _ = state(tmp_path)
    saved = worker.save(guard())
    mutate(worker)
    commands.fail = phase
    with pytest.raises(OSError) as raised:
        worker.restore(saved, guard())
    assert getattr(raised.value, "admin_restore_mutation_attempted") is True
    assert getattr(raised.value, "admin_state_snapshot") == saved
    expected: tuple[str, ...] = (
        () if phase == "restore" else ("database", "declared_artifacts")
    )
    if phase == "search:restore":
        expected += ("application_cache_and_redis",)
    assert getattr(raised.value, "admin_restore_completed") == expected
    assert worker.quarantined and not worker.busy
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        worker.restore(saved, guard())
    assert len(commands.calls) == count


def test_file_restore_failure_keeps_database_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, commands, _ = state(tmp_path)
    saved = worker.save(guard())
    error = OSError("file mutation failed")

    def failed(*args: Any) -> Any:
        raise error

    monkeypatch.setattr(worker.artifacts, "restore", failed)
    with pytest.raises(OSError) as caught:
        worker.restore(saved, guard())
    assert caught.value is error and getattr(error, "admin_restore_completed") == (
        "database",
    )
    assert all(v[-1] != "FLUSHALL" for v in commands.calls)


@pytest.mark.parametrize("phase", ["search", "database", "artifacts", "after_save"])
def test_failed_save_retains_partial_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    worker, commands, _ = state(tmp_path)
    if phase == "search":
        commands.fail = "search:save"
    if phase == "database":
        commands.fail = "save"
    if phase == "artifacts":
        worker.artifacts.backup.mkdir()

    completed = False
    original_save = worker.artifacts.save

    def save_files(control: OperationControl) -> Any:
        nonlocal completed
        result = original_save(control)
        completed = True
        return result

    monkeypatch.setattr(worker.artifacts, "save", save_files)

    class StopAfter:
        def checkpoint(self) -> float:
            if phase == "after_save" and completed:
                raise TimeoutError("after snapshot")
            return 30.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises((OSError, TimeoutError)) as caught:
        worker.save(StopAfter())
    assert worker.quarantined and not worker.busy
    assert (getattr(caught.value, "admin_database_snapshot") is not None) == (
        phase not in ("search", "database")
    )
    if phase == "after_save":
        assert getattr(caught.value, "admin_artifact_snapshot") is not None
    with pytest.raises(RuntimeError):
        worker.save(guard())


def test_permission_denied_save_no_effect_and_reentrancy_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, commands, authority = state(tmp_path)
    authority.deny = True
    with pytest.raises(PermissionError):
        worker.save(guard())
    assert not commands.calls and not worker.save_attempted and not worker.quarantined

    def reenter(*args: Any) -> None:
        worker.save(guard())

    monkeypatch.setattr(authority, "verify", reenter)
    with pytest.raises(RuntimeError, match="busy"):
        worker.save(guard())
    assert not commands.calls and not worker.busy


@pytest.mark.parametrize(
    "field,value",
    [
        ("instance_id", "foreign"),
        ("app_root", "/tmp/other/app"),
        ("node_root", "/tmp/other"),
    ],
)
def test_plan_cannot_mix_original_layouts(
    tmp_path: Path, field: str, value: Any
) -> None:
    worker, _, _ = state(tmp_path)
    data = worker.plan.model_dump()
    data["artifacts"][field] = value
    with pytest.raises(ValueError):
        AdminStatePlan.model_validate(data)


@pytest.mark.parametrize("raw", [b"", b"ERR failed\n", b"OK\nextra", b"+OK\n"])
def test_cache_failed_ack_stops_without_readback(tmp_path: Path, raw: bytes) -> None:
    commands = Commands()
    commands.flush = raw
    with pytest.raises(ValueError):
        AdminCaches(spec(tmp_path), commands).reset(guard())
    assert len(commands.calls) == 2


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"# Keyspace\r\ndb1:keys=1,expires=0,avg_ttl=0\r\n",
        b"ERR bad\n",
        b"# Keyspace\nunknown",
        b"# Keyspace\r",
    ],
)
def test_all_database_keyspace_must_be_empty(tmp_path: Path, raw: bytes) -> None:
    commands = Commands()
    commands.keyspace = raw
    with pytest.raises(ValueError):
        AdminCaches(spec(tmp_path), commands).reset(guard())
    assert len(commands.calls) == 3


def test_cache_uses_exact_declared_server_not_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WA_ADMIN_REDIS_PORT", "1")
    commands = Commands()
    service = spec(tmp_path)
    reply = AdminCaches(service, commands).reset(guard())
    assert reply.service == service
    assert commands.calls[1][-6:] == (
        "--raw",
        "-h",
        "127.0.0.1",
        "-p",
        str(service.ports.redis),
        "FLUSHALL",
    )


def test_artifact_verify_is_readonly_even_when_target_differs(tmp_path: Path) -> None:
    worker, _, _ = state(tmp_path)
    saved = worker.save(guard())
    path = mutate(worker)
    assert worker.artifacts.verify(saved.artifacts, guard()) == saved.artifacts
    assert path.read_bytes() == b"changed"


@pytest.mark.parametrize(
    "field", ["application_cache_command_succeeded", "redis_all_databases_empty"]
)
@pytest.mark.parametrize("value", [1, 0, "true", None, False])
def test_cache_facts_reject_coerced_success(
    tmp_path: Path, field: str, value: Any
) -> None:
    from lab_generate_skill.sites.shopping_admin.cache_contract import AdminCacheReset

    data: dict[str, Any] = dict(
        service=spec(tmp_path),
        application_cache_command_succeeded=True,
        redis_all_databases_empty=True,
    )
    data[field] = value
    with pytest.raises(ValueError):
        AdminCacheReset.model_validate(data)


@pytest.mark.parametrize("field", ["schema_version", "search", "foreign_search"])
def test_composed_snapshot_requires_current_original_search(
    tmp_path: Path, field: str
) -> None:
    worker, commands, _ = state(tmp_path)
    saved = worker.save(guard())
    data = saved.model_dump()
    if field == "schema_version":
        data[field] = "admin-state-snapshot/1"
    elif field == "search":
        del data[field]
    else:
        data["search"]["service"]["ports"]["search"] += 1
    before = len(commands.calls)
    with pytest.raises(ValueError):
        worker.restore(data, guard())  # type: ignore[arg-type]
    assert len(commands.calls) == before


def test_search_save_final_stop_retains_descriptor_before_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, commands, _ = state(tmp_path)
    control = guard()

    def stop() -> float:
        raise TimeoutError("after search save")

    commands.search_commands.after = lambda: monkeypatch.setattr(
        control, "checkpoint", stop
    )
    with pytest.raises(TimeoutError) as caught:
        worker.save(control)
    assert getattr(caught.value, "admin_search_snapshot") is not None
    assert getattr(caught.value, "admin_database_snapshot") is None
    assert [command_phase(c) for c in commands.calls] == ["search:save"]
    assert worker.quarantined
