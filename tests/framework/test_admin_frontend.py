"""Frontend stops before backend drain; busy/error/unknown never grants restore."""

from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.backend_drain import (
    AdminDrain,
    redis_clients,
)
from lab_generate_skill.sites.shopping_admin.frontend import AdminFrontend
from lab_generate_skill.sites.shopping_admin.frontend_contract import (
    AdminFrontendStopped,
)
from lab_generate_skill.sites.shopping_admin.drain_program import (
    DATABASE_DRAIN_PHP,
    SEARCH_DRAIN_PHP,
)
from test_admin_services import Services, spec
from test_slurm_commands import guard
from frontend_fixtures import frontend


class Commands:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.sql: Any = {"other_sql_connections": 0, "sql_transactions": 0}
        self.search: Any = {"search_write_tasks": 0}
        self.redis = b"# Clients\r\nconnected_clients:1\r\nblocked_clients:0\r\n\r\n"
        self.fail: str | None = None
        self.clear_after: int | None = None

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        phase = (
            "sql"
            if DATABASE_DRAIN_PHP in argv
            else "search" if SEARCH_DRAIN_PHP in argv else "redis"
        )
        self.calls.append(phase)
        if phase == self.fail:
            raise OSError("original " + phase + " failure")
        if phase == "sql":
            value = self.sql
            if (
                self.clear_after is not None
                and self.calls.count("sql") > self.clear_after
            ):
                value = {"other_sql_connections": 0, "sql_transactions": 0}
            return json.dumps(value).encode()
        if phase == "search":
            return json.dumps(self.search).encode()
        return self.redis


def test_normal_namespace_order_and_busy_readonly_poll(tmp_path: Path) -> None:
    services, commands = Services(), Commands()
    commands.sql["sql_transactions"] = 1
    commands.clear_after = 1
    barrier = AdminFrontend(spec(tmp_path), commands, services)
    barrier.pin(guard())
    facts = barrier.stop(guard())
    assert services.pins == services.closed_namespaces == ["nginx", "php"]
    assert facts == frontend(spec(tmp_path))
    assert commands.calls == ["sql", "redis", "search"] * 2
    with pytest.raises(RuntimeError):
        barrier.stop(guard())
    with pytest.raises(RuntimeError):
        barrier.pin(guard())
    assert services.closed_namespaces == ["nginx", "php"]


@pytest.mark.parametrize("failure", ["nginx", "php", "sql", "redis", "search"])
def test_partial_failure_keeps_closed_prefix_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    services, commands = Services(), Commands()
    barrier = AdminFrontend(spec(tmp_path), commands, services)
    barrier.pin(guard())
    original = services.stop_namespace

    def stop(name: str, control: OperationControl) -> Any:
        if name == failure:
            raise OSError("original " + name + " failure")
        return original(name, control)

    monkeypatch.setattr(services, "stop_namespace", stop)
    commands.fail = failure
    with pytest.raises(OSError) as caught:
        barrier.stop(guard())
    expected = 0 if failure == "nginx" else 1 if failure == "php" else 2
    assert len(getattr(caught.value, "admin_frontend_completed")) == expected
    if failure in ("nginx", "php"):
        assert not commands.calls
    before = list(commands.calls)
    with pytest.raises(RuntimeError):
        barrier.stop(guard())
    assert commands.calls == before


@pytest.mark.parametrize(
    "phase,bad",
    [
        ("sql", {}),
        ("sql", {"other_sql_connections": False, "sql_transactions": 0}),
        ("sql", {"other_sql_connections": 0, "sql_transactions": -1}),
        ("search", []),
        ("search", {"search_write_tasks": "0"}),
        ("search", {"search_write_tasks": 0, "extra": 1}),
    ],
)
def test_bad_backend_reply_has_no_retry(tmp_path: Path, phase: str, bad: Any) -> None:
    commands = Commands()
    setattr(commands, phase, bad)
    with pytest.raises(ValueError):
        AdminDrain(spec(tmp_path), commands).wait(guard())
    assert commands.calls.count(phase) == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"ERR error\r\n",
        b"# Clients\r\n",
        b"# Clients\r\nconnected_clients:1\r\nconnected_clients:1\r\nblocked_clients:0\r\n",
        b"# Clients\r\nconnected_clients:-1\r\nblocked_clients:0\r\n",
        b"# Clients\r\nconnected_clients:1\r\nblocked_clients:0",
    ],
)
def test_redis_counts_must_be_complete_and_unique(raw: bytes) -> None:
    with pytest.raises(ValueError):
        redis_clients(raw)


def test_busy_backend_deadline_keeps_last_observation(tmp_path: Path) -> None:
    commands = Commands()
    commands.sql["sql_transactions"] = 1

    class Deadline:
        def checkpoint(self) -> float:
            return 0.1

        def wait(self, seconds: float) -> None:
            raise TimeoutError("original drain deadline")

    with pytest.raises(TimeoutError) as caught:
        AdminDrain(spec(tmp_path), commands).wait(Deadline())
    assert not getattr(caught.value, "admin_backend_drain").drained
    assert commands.calls == ["sql", "redis", "search"]


def test_restore_fact_rejects_same_namespace_or_busy_backend(tmp_path: Path) -> None:
    value = frontend(spec(tmp_path))
    for changes in (
        {"namespaces": (value.namespaces[0], value.namespaces[0])},
        {"backend": value.backend.model_copy(update={"sql_transactions": 1})},
    ):
        with pytest.raises(ValueError):
            AdminFrontendStopped.model_validate(value.model_copy(update=changes))
