"""Actual state restore followed by explicit frontend recovery on original ports."""

from pathlib import Path
from typing import Any
import urllib.request
from lab_generate_skill.sites.shopping_admin.instance import AdminInstance
from lab_generate_skill.sites.shopping_admin.state import AdminState
from lab_generate_skill.sites.shopping_admin.state_contract import (
    AdminStatePlan,
    AdminStateRestored,
)
from lab_generate_skill.sites.shopping_admin.artifact_contract import (
    AdminArtifactLayout,
    ARTIFACT_PATHS,
)
from lab_generate_skill.sites.shopping_admin.frontend_contract import (
    AdminFrontendStopped,
)
from lab_generate_skill.sites.shopping_admin.service_commands import container
from lab_generate_skill.ports.lifecycle import OperationControl
from test_admin_services_native import run_admin_services_probe
from test_admin_state_native import EngineeringAuthority
from test_admin_search_native import Authority as SearchAuthority
from test_admin_database_native import PDO
from test_slurm_commands import guard


class RecoveryAuthority:
    def __init__(
        self,
        site: AdminInstance,
        stopped: AdminFrontendStopped,
        restored: AdminStateRestored,
    ) -> None:
        self.site, self.stopped, self.restored = site, stopped, restored

    def verify(
        self,
        stopped: AdminFrontendStopped,
        restored: AdminStateRestored,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert (stopped, restored) == (self.stopped, self.restored)
        assert self.site.port_lease is not None and self.site.spec is not None
        assert stopped.service == self.site.spec
        assert self.site.state == "recovering_frontend"
        # Sole engineering fixture; no browser, source claim or Actor permission.


def probe(site: AdminInstance) -> dict[str, Any]:
    service = site.spec
    assert service is not None
    root = Path(service.layout.node_root)
    plan = AdminStatePlan(
        service=service,
        artifacts=AdminArtifactLayout(
            instance_id=service.layout.instance_id,
            node_root=str(root),
            app_root=service.layout.state_root + "/app",
            backup_root=str(root / "frontend-state-backup"),
            paths=tuple(sorted(ARTIFACT_PATHS)),
        ),
    )
    state = AdminState(
        plan, site.commands, EngineeringAuthority(plan), SearchAuthority(service)
    )
    base = container(service)
    site.commands.run(
        base
        + (
            "php",
            "-r",
            PDO
            + "$p->exec('CREATE TABLE frontend_recovery_probe(id INT PRIMARY KEY,value INT)');$p->exec('INSERT INTO frontend_recovery_probe VALUES(1,10)');",
        ),
        guard(20),
    )
    snapshot = state.save(guard(120))
    stopped = site.stop_frontend(guard(30))
    site.commands.run(
        base
        + (
            "php",
            "-r",
            PDO + "$p->exec('UPDATE frontend_recovery_probe SET value=20');",
        ),
        guard(20),
    )
    restored = state.restore(snapshot, guard(120))
    assert (
        site.commands.run(
            base
            + (
                "php",
                "-r",
                PDO
                + "echo $p->query('SELECT value FROM frontend_recovery_probe')->fetchColumn();",
            ),
            guard(20),
        )
        == b"10"
    )
    recovered = site.recover_frontend(
        restored, RecoveryAuthority(site, stopped, restored), guard(60)
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        service.admin_url, timeout=10
    ) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        assert response.status == 200 and len(body) <= 2 * 1024 * 1024
        assert b"login" in body.lower() or b"sign in" in body.lower()
    assert site.services is not None and site.services.frontend.result == stopped
    assert tuple(site.services.frontend.pins) == tuple(
        p.original for p in stopped.namespaces
    )
    return dict(
        restored=restored.model_dump(mode="json"),
        recovered=recovered.model_dump(mode="json"),
        same_ports=True,
        old_namespace_facts_retained=True,
        login_after_restore=True,
        original_database_value_restored=True,
        actor_authorized=False,
        complete_reset_receipt=False,
    )


def test_actual_original_state_restore_frontend_health_and_all_generations_stop() -> (
    None
):
    run_admin_services_probe(instance_probe=probe)
