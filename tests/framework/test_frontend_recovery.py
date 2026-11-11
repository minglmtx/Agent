"""Confirmed predecessor, distinct generation, mandatory admission and no retries."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.frontend_recovery_contract import (
    AdminFrontendRecovered,
)
from lab_generate_skill.sites.shopping_admin.frontend_recovery import (
    AdminFrontendRecovery,
)
from frontend_recovery_fixtures import fixture
from test_slurm_commands import guard


def test_original_stopped_facts_and_new_generation_health(tmp_path: Path) -> None:
    recovery, commands, group, authority = fixture(tmp_path)
    original = recovery.stopped.model_dump_json()
    commands.health["frontend"] = [b"waiting", b"ready"]
    result = recovery.recover(guard())
    assert result.stopped.model_dump_json() == original
    assert (
        result.before_start.drained and result.backend_ready and result.frontend_ready
    )
    assert group.names == [
        "mysql",
        "redis",
        "search",
        "php",
        "nginx",
        "php-restored",
        "nginx-restored",
    ]
    assert group.pins == ["php-restored", "nginx-restored"]
    assert commands.calls == [
        "sql",
        "redis",
        "search",
        "health:backend",
        "config:nginx",
        "config:php",
        "health:frontend",
        "health:frontend",
    ]
    assert authority.calls == 1
    with pytest.raises(RuntimeError, match="already attempted"):
        recovery.recover(guard())
    assert len(group.names) == 7


def test_denied_permission_has_no_command_or_launch(tmp_path: Path) -> None:
    recovery, commands, group, authority = fixture(tmp_path)
    authority.denied = True
    with pytest.raises(PermissionError):
        recovery.recover(guard())
    assert not commands.calls and len(group.names) == 5


def test_cancel_before_admission_has_no_effect(tmp_path: Path) -> None:
    recovery, commands, group, authority = fixture(tmp_path)

    class Cancelled:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled before admission")

        def wait(self, seconds: float) -> None:
            raise AssertionError("no wait before admission")

    with pytest.raises(TimeoutError):
        recovery.recover(Cancelled())
    assert authority.calls == 0 and not recovery.attempted
    assert not commands.calls and len(group.names) == 5


def test_foreign_state_restore_rejected_before_commands(tmp_path: Path) -> None:
    recovery, commands, group, authority = fixture(tmp_path)
    foreign = recovery.restored.model_copy(
        update={
            "cache": recovery.restored.cache.model_copy(
                update={
                    "service": recovery.stopped.service.model_copy(
                        update={"admin_url": "http://127.0.0.1:1/admin"}
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError):
        AdminFrontendRecovery(
            recovery.stopped,
            foreign,
            commands=commands,
            services=group,
            authority=authority,
        )
    assert not commands.calls and len(group.names) == 5


@pytest.mark.parametrize(
    "failure",
    [
        "sql",
        "redis",
        "search",
        "backend",
        "nginx-config",
        "php-config",
        "php-start",
        "nginx-start",
        "php-pin",
        "nginx-pin",
        "frontend",
    ],
)
def test_fault_retains_exact_attempted_and_confirmed_prefix(
    tmp_path: Path, failure: str
) -> None:
    recovery, commands, group, _ = fixture(tmp_path)
    if failure in ("sql", "redis", "search"):
        commands.fail = failure
    elif failure == "backend":
        commands.health["backend"] = [b"waiting"]
    elif failure.endswith("-config"):
        commands.configuration_failure = failure.split("-")[0]
    elif failure.endswith("-start"):
        group.fail = failure.split("-")[0] + "-restored"
    elif failure.endswith("-pin"):
        group.pin_failure = failure.split("-")[0] + "-restored"
    else:
        commands.health["frontend"] = [b"malformed"]
    with pytest.raises((OSError, ValueError, RuntimeError)) as caught:
        recovery.recover(guard())
    attempted = getattr(caught.value, "admin_frontend_recovery_attempted")
    assert attempted == tuple(group.names[5:])
    assert getattr(caught.value, "admin_frontend_recovery_launched") == tuple(
        recovery.launched
    )
    assert getattr(caught.value, "admin_frontend_recovery_pins") == tuple(recovery.pins)
    assert getattr(caught.value, "admin_frontend_recovered") is None
    before = (list(commands.calls), list(group.names))
    with pytest.raises(RuntimeError):
        recovery.recover(guard())
    assert before == (commands.calls, group.names)
    group.stop(guard())
    assert group.stopped


def test_old_or_foreign_namespace_cannot_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recovery, _, group, _ = fixture(tmp_path)

    def old(name: str, control: OperationControl) -> NativeNamespaceIdentity:
        value = next(
            p.original
            for p in recovery.stopped.namespaces
            if p.original.service == name.removesuffix("-restored")
        )
        return value.model_copy(update={"service": name})

    monkeypatch.setattr(group, "pin_namespace", old)
    with pytest.raises(ValueError, match="reuse"):
        recovery.recover(guard())


@pytest.mark.parametrize(
    "field,value",
    [
        ("backend_ready", False),
        ("frontend_ready", False),
        ("schema_version", "old/1"),
        ("namespaces", ()),
    ],
)
def test_incomplete_health_cannot_be_a_recovered_fact(
    tmp_path: Path, field: str, value: Any
) -> None:
    recovery, _, _, _ = fixture(tmp_path)
    result = recovery.recover(guard())
    with pytest.raises(ValueError):
        AdminFrontendRecovered.model_validate({**result.model_dump(), field: value})


def test_health_deadline_retains_launches_without_premature_pins(
    tmp_path: Path,
) -> None:
    recovery, commands, group, _ = fixture(tmp_path)
    commands.health["frontend"] = [b"waiting"]

    class Deadline:
        def checkpoint(self) -> float:
            return 0.1

        def wait(self, seconds: float) -> None:
            raise TimeoutError("original recovery deadline")

    with pytest.raises(TimeoutError) as caught:
        recovery.recover(Deadline())
    assert getattr(caught.value, "admin_frontend_recovery_pins") == ()
    assert getattr(caught.value, "admin_frontend_recovery_launched") == (
        "php-restored",
        "nginx-restored",
    )
    assert not group.pins
    assert len(group.names) == 7


def test_namespace_pin_waits_for_both_launches_and_healthy_frontend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recovery, commands, group, _ = fixture(tmp_path)
    commands.health["frontend"] = [b"waiting", b"ready"]
    original = group.pin_namespace

    def pin(name: str, control: OperationControl) -> NativeNamespaceIdentity:
        assert group.names[-2:] == ["php-restored", "nginx-restored"]
        assert commands.calls[-2:] == ["health:frontend", "health:frontend"]
        assert commands.health["frontend"] == [b"ready"]
        return original(name, control)

    monkeypatch.setattr(group, "pin_namespace", pin)
    recovery.recover(guard())
