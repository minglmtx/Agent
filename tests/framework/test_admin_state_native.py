"""Real private-image DB/files/cache composition, explicitly engineering admission."""

from pathlib import Path
from typing import Any, Literal
import pytest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.service_commands import container
from lab_generate_skill.sites.shopping_admin.state import AdminState
from lab_generate_skill.sites.shopping_admin.state_contract import (
    AdminStatePlan,
    AdminStateSnapshot,
)
from lab_generate_skill.sites.shopping_admin.artifact_contract import (
    AdminArtifactLayout,
    ARTIFACT_PATHS,
)
from lab_generate_skill.sites.shopping_admin.database_script import (
    DATABASE_SNAPSHOT_PHP,
)
from test_admin_database_native import PDO
from test_admin_services_native import run_admin_services_probe
from test_slurm_commands import guard
from test_admin_search_native import Authority as SearchAuthority, PROBE as SEARCH_PROBE
from lab_generate_skill.sites.shopping_admin.search_program import SEARCH_SNAPSHOT_PHP


class EngineeringAuthority:
    def __init__(self, plan: AdminStatePlan) -> None:
        self.plan = plan

    def verify(
        self,
        plan: AdminStatePlan,
        phase: Literal["save", "restore"],
        snapshot: AdminStateSnapshot | None,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert plan == self.plan
        if phase == "save":
            assert snapshot is None
        else:
            assert snapshot is not None and snapshot.plan == plan
        # Sole test owner; no browser/Actor or other client runs in this fixture.
        # This is not production writer/claim or whole-site restoration authority.


def probe(service: AdminServiceSpec, commands: NativeCommands) -> dict[str, Any]:
    root = Path(service.layout.node_root)
    app = Path(service.layout.state_root) / "app"
    message = app / "var/training-mail/message"
    message.parent.mkdir(parents=True, exist_ok=True)
    message.write_bytes(b"original\0mail")
    message.chmod(0o640)
    plan = AdminStatePlan(
        service=service,
        artifacts=AdminArtifactLayout(
            instance_id=service.layout.instance_id,
            node_root=str(root),
            app_root=str(app),
            backup_root=str(root / "state-backup"),
            paths=tuple(sorted(ARTIFACT_PATHS)),
        ),
    )
    authority = EngineeringAuthority(plan)
    worker = AdminState(plan, commands, authority, SearchAuthority(service))
    base = container(service)

    def sql(code: str) -> bytes:
        return commands.run(base + ("php", "-r", PDO + code), guard(30))

    redis = base + (
        "redis-cli",
        "--raw",
        "-h",
        "127.0.0.1",
        "-p",
        str(service.ports.redis),
    )
    sql(
        "$p->exec('CREATE TABLE framework_state_probe(id INT PRIMARY KEY, value VARCHAR(20))');$p->exec(\"INSERT INTO framework_state_probe VALUES(1, 'original')\");"
    )

    def search(phase: str) -> None:
        assert (
            commands.run(
                base + ("php", "-r", SEARCH_PROBE, str(service.ports.search), phase),
                guard(30),
            )
            == b"ok"
        )

    search("seed")
    snapshot = worker.save(guard(120))
    persisted = AdminStateSnapshot.model_validate_json(snapshot.model_dump_json())
    dump = Path(service.layout.state_root) / "framework-db-baseline.sql"
    before = dump.stat()
    verification = worker.database.verify(persisted.database, guard(30))
    assert (
        verification.operation == "verify"
        and dump.stat().st_mtime_ns == before.st_mtime_ns
    )
    assert (
        sql("echo $p->query('SELECT value FROM framework_state_probe')->fetchColumn();")
        == b"original"
    )
    sql(
        "$p->exec(\"UPDATE framework_state_probe SET value='changed'\");$p->exec('CREATE TABLE framework_state_extra(id INT)');"
    )
    search("mutate")
    message.write_bytes(b"changed")
    message.chmod(0o600)
    added = app / "pub/media/training-assets"
    assert not added.exists()
    added.mkdir(parents=True)
    (added / "unexpected").write_bytes(b"extra")
    for db in ("0", "1"):
        assert (
            commands.run(
                redis + ("-n", db, "SET", "framework-state-probe", "changed"), guard(10)
            ).strip()
            == b"OK"
        )
    result = AdminState(plan, commands, authority, SearchAuthority(service)).restore(
        persisted, guard(120)
    )
    search("verify")
    assert result.search.original == persisted.search
    assert (
        result.snapshot_sha256 == snapshot.digest
        and result.cache.redis_all_databases_empty
    )
    assert (
        sql("echo $p->query('SELECT value FROM framework_state_probe')->fetchColumn();")
        == b"original"
    )
    assert (
        sql(
            "echo $p->query(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='framework_state_extra'\")->fetchColumn();"
        )
        == b"0"
    )
    assert (
        message.read_bytes() == b"original\0mail"
        and message.stat().st_mode & 0o777 == 0o640
        and not added.exists()
    )
    for db in ("0", "1"):
        assert commands.run(redis + ("-n", db, "DBSIZE"), guard(10)).strip() == b"0"
    # Corrupt only a known original backup. The DB sentinel must survive rejection.
    sql("$p->exec(\"UPDATE framework_state_probe SET value='untouched'\");")
    index = plan.artifacts.paths.index("var/training-mail")
    (Path(plan.artifacts.backup_root) / str(index) / "message").write_bytes(b"corrupt")
    with pytest.raises(ValueError) as caught:
        AdminState(plan, commands, authority, SearchAuthority(service)).restore(
            persisted, guard(60)
        )
    assert getattr(caught.value, "admin_restore_mutation_attempted") is False
    assert (
        sql("echo $p->query('SELECT value FROM framework_state_probe')->fetchColumn();")
        == b"untouched"
    )
    return dict(
        snapshot=snapshot.model_dump(mode="json"),
        restore=result.model_dump(mode="json"),
        database_preflight_readonly=True,
        original_row_restored=True,
        new_table_removed=True,
        original_files_and_permissions_restored=True,
        original_absence_restored=True,
        redis_databases_zero_and_one_empty=True,
        corrupt_file_backup_rejected_before_database_mutation=True,
        formal_restore_authority=False,
        search_state_verified=True,
        complete_site_reset=False,
    )


def test_real_original_database_files_and_cache_restore() -> None:
    run_admin_services_probe(
        probe, programs=(DATABASE_SNAPSHOT_PHP, PDO, SEARCH_SNAPSHOT_PHP, SEARCH_PROBE)
    )
