"""Owned instance retains old/new generations and closes all partial starts."""

from pathlib import Path
import pytest
from lab_generate_skill.sites.shopping_admin.instance import AdminInstance
from lab_generate_skill.sites.shopping_admin.state_contract import AdminStateRestored
from site_instance_fixtures import node_path as node_path
from test_admin_instance import instance, Group
from test_admin_state import state
from frontend_fixtures import frontend
from frontend_recovery_fixtures import Commands, Authority, recovered_namespace
from test_slurm_commands import guard


def ready(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AdminInstance, AdminStateRestored, Authority, Group]:
    site, _, group, _ = instance(node_path)
    service = site.prepare(guard())
    site.start(guard())
    worker, _, _ = state(Path(service.layout.node_root), service=service)
    saved = worker.save(guard())
    restored = worker.restore(saved, guard())
    stopped = frontend(service)
    assert site.services is not None
    site.services.frontend.result = stopped
    site.state = "quiesced"
    site.commands = Commands()
    monkeypatch.setattr(
        group, "pin_namespace", lambda name, control: recovered_namespace(name)
    )
    return site, restored, Authority(stopped, restored), group


@pytest.mark.parametrize("failed_start", [None, "nginx-restored"])
def test_same_instance_closes_old_and_new_generation(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, failed_start: str | None
) -> None:
    site, restored, authority, group = ready(node_path, monkeypatch)
    group.fail = failed_start
    if failed_start is not None:
        with pytest.raises(OSError):
            site.recover_frontend(restored, authority, guard())
        assert site.state == "failed"
    else:
        result = site.recover_frontend(restored, authority, guard())
        assert result.frontend_ready and site.state == "recovered"
    with pytest.raises(RuntimeError):
        site.recover_frontend(restored, authority, guard())
    facts = site.stop(guard())
    assert tuple(f.service for f in facts) == (
        "mysql",
        "redis",
        "search",
        "php",
        "nginx",
        "php-restored",
        "nginx-restored",
    )
    assert site.state == "stopped" and site.port_lease is not None
    assert not site.port_lease.released  # type: ignore[attr-defined]


def test_live_or_foreign_frontend_is_not_recovered(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site, restored, authority, group = ready(node_path, monkeypatch)
    site.state = "ready"
    with pytest.raises(RuntimeError, match="quiesced"):
        site.recover_frontend(restored, authority, guard())
    assert len(group.names) == 5 and site.frontend_recovery is None
    site.stop(guard())
