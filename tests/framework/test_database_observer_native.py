"""Real authorized initialization and visibility, with no added DB accounts."""

import json
from pathlib import Path
import subprocess
import pytest
from database_observer_native_fixtures import database, observer_image as observer_image
from test_admin_database_native import PDO
from test_slurm_commands import guard
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.adapters.processes.pid_namespace import HeldPidNamespace
from lab_generate_skill.sites.shopping_admin.database_observer import (
    require_initial_idle,
)
from lab_generate_skill.sites.shopping_admin.drain_program import DATABASE_DRAIN_PHP
from lab_generate_skill.sites.shopping_admin.service_commands import container


def test_real_authorized_observation_and_busy_transaction(observer_image: Path) -> None:
    with database(observer_image, "authorized") as db:
        original = (db.state / "app/app/etc/env.php").read_bytes()
        db.start("authorized")
        assert db.server is not None and db.server.poll() is None
        require_initial_idle(db.spec, db.commands, guard(20))
        assert (db.state / "app/app/etc/env.php").read_bytes() == original
        assert (
            db.run(PDO + "echo 'original-credentials-valid';")
            == b"original-credentials-valid"
        )
        init = db.state / "database-observer-init.sql"
        assert init.stat().st_mode & 0o777 == 0o600
        db.run(
            PDO
            + "$p->exec('CREATE TABLE framework_visibility_probe (id INT PRIMARY KEY, value INT) ENGINE=InnoDB');$p->exec('INSERT INTO framework_visibility_probe VALUES (1,0)');"
        )
        holder_program = (
            PDO
            + "$p->beginTransaction();$p->exec('UPDATE framework_visibility_probe SET value=1 WHERE id=1');file_put_contents('/state/transaction-ready','ready');fgets(STDIN);$p->rollBack();"
        )
        with (db.output / "transaction.log").open("wb") as log:
            holder = subprocess.Popen(
                container(db.spec) + ("php", "-r", holder_program),
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        held = None
        try:
            ready = guard(15)
            while not (db.state / "transaction-ready").exists():
                assert holder.poll() is None
                ready.wait(0.05)
            held = HeldPidNamespace("transaction", holder, guard(10))
            # INNODB_TRX refresh has bounded lag; only valid busy counts are observed.
            waiting = guard(10)
            while True:
                counts = json.loads(db.run(DATABASE_DRAIN_PHP))
                assert counts["other_sql_connections"] >= 1
                if counts["sql_transactions"] >= 1:
                    break
                waiting.wait(0.2)
            with pytest.raises(ValueError, match="complete idle"):
                require_initial_idle(db.spec, db.commands, guard(20))
            db.facts["busy_counts"] = counts
            assert holder.stdin is not None
            holder.stdin.write(b"release\n")
            holder.stdin.flush()
            holder.stdin.close()
            assert holder.wait(timeout=10) == 0
        finally:
            if held is not None:
                db.facts["transaction_stop"] = held.stop(guard(10)).model_dump(
                    mode="json"
                )
                held.close()
        waiting = guard(10)
        while True:
            final = json.loads(db.run(DATABASE_DRAIN_PHP))
            if final == {"other_sql_connections": 0, "sql_transactions": 0}:
                break
            waiting.wait(0.2)
        require_initial_idle(db.spec, db.commands, guard(20))
        db.facts.update(
            original_credentials_valid=True, config_unchanged=True, final_counts=final
        )


@pytest.mark.parametrize("scenario", ["no_process", "missing_account", "broken_init"])
def test_real_missing_visibility_never_admits_frontend(
    observer_image: Path, scenario: str
) -> None:
    with database(observer_image, scenario) as db:
        db.start(scenario)
        if db.server is not None and db.server.poll() is not None:
            assert scenario != "no_process"
            db.facts["rejected_before_frontend"] = "server_exited"
            return
        with pytest.raises(CommandFailure) as raised:
            require_initial_idle(db.spec, db.commands, guard(20))
        stderr = raised.value.capture.stderr
        (db.output / "rejection-stderr.bin").write_bytes(stderr)
        if scenario != "missing_account":
            assert b"Complete SQL process visibility required" in stderr
        else:
            assert b"Access denied" in stderr
        db.facts["rejected_before_frontend"] = True
