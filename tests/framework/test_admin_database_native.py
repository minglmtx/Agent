"""Real pinned-image MySQL save/mutate/restore; no website or training admission."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.adapters.processes.cleanup import finish_process
from lab_generate_skill.sites.shopping_admin.database import AdminDatabase
from lab_generate_skill.sites.shopping_admin.database_contract import (
    AdminDatabaseLayout,
    AdminDatabaseSnapshot,
)
from lab_generate_skill.sites.shopping_admin.database_script import (
    DATABASE_SNAPSHOT_PHP,
)
from test_slurm_commands import guard

IMAGE_SHA = "875f0bf95becbb268a1a7491459ff69f86ec956e2740ec75be2b48f0ee69379a"
IMAGE = (
    Path("/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/shopping-admin")
    / IMAGE_SHA
    / "shopping-admin.sif"
)
PDO = "$e=include '/state/app/app/etc/env.php';$d=$e['db']['connection']['default'];$p=new PDO('mysql:unix_socket=/state/run/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);"


def test_real_database_snapshot_restores_rows_and_removes_added_table() -> None:
    assert os.environ.get("SLURM_JOB_ID")
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    facts: dict[str, Any] = {
        "passed": False,
        "engineering_only": True,
        "actual_website_preparation": False,
        "image_sha256": IMAGE_SHA,
    }
    server: subprocess.Popen[bytes] | None = None
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lab-admin-db-", dir="/tmp") as directory:
        root = Path(directory)
        state = root / "state"
        state.mkdir(mode=0o700)
        image = root / "admin.sif"
        shutil.copyfile(IMAGE, image)
        digest = hashlib.sha256()
        with image.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        assert digest.hexdigest() == IMAGE_SHA
        image.chmod(0o400)
        facts["image_copy_verify_seconds"] = time.monotonic() - started
        commands = CheckedNativeCommands(ProcessRunner(max_output_bytes=128 * 1024))
        base = (
            "/usr/bin/apptainer",
            "exec",
            "--cleanenv",
            "--containall",
            "--no-home",
            "--no-mount",
            "bind-paths,hostfs,cwd",
            "--pwd",
            "/",
            "--bind",
            str(state) + ":/state",
            str(image),
        )
        # Lint the exact fixed program before DB extraction/service startup.
        (state / "snapshot-check.php").write_text("<?php\n" + DATABASE_SNAPSHOT_PHP)
        lint = commands.run(
            base + ("php", "-l", "/state/snapshot-check.php"), guard(30)
        )
        assert b"No syntax errors" in lint
        facts["php_lint"] = lint.decode()
        extract = "cp -a /var/lib/mysql /state/mysql; chmod -R u+rwX /state/mysql; mkdir -p /state/run /state/app/app/etc; cp /var/www/magento2/app/etc/env.php /state/app/app/etc/env.php; chmod u+rw /state/app/app/etc/env.php"
        extract_started = time.monotonic()
        commands.run(base + ("sh", "-ec", extract), guard(90))
        facts["database_seed_extract_seconds"] = time.monotonic() - extract_started
        service_log = output / "admin-database-service.log"
        with service_log.open("wb") as log:
            try:
                server = subprocess.Popen(
                    base
                    + (
                        "mysqld",
                        "--no-defaults",
                        "--datadir=/state/mysql",
                        "--socket=/state/run/mysql.sock",
                        "--pid-file=/state/run/mysql.pid",
                        "--skip-networking",
                        "--innodb-buffer-pool-size=128M",
                    ),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                    start_new_session=True,
                )
                ready = guard(45)
                while True:
                    if server.poll() is not None:
                        raise RuntimeError("Original MySQL exited; inspect service log")
                    if (state / "run/mysql.sock").is_socket():
                        try:
                            commands.run(
                                base
                                + (
                                    "mysqladmin",
                                    "--no-defaults",
                                    "--socket=/state/run/mysql.sock",
                                    "ping",
                                ),
                                ready,
                            )
                            break
                        except CommandFailure as error:
                            if error.capture.returncode not in (1,):
                                raise
                    ready.wait(0.25)

                def sql(program: str) -> bytes:
                    return commands.run(base + ("php", "-r", PDO + program), guard(30))

                sql(
                    "$p->exec('CREATE TABLE framework_snapshot_probe (id INT PRIMARY KEY, value VARCHAR(20))');$p->exec(\"INSERT INTO framework_snapshot_probe VALUES (1, 'original')\");"
                )
                count = sql(
                    "echo $p->query('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')->fetchColumn();"
                )
                layout = AdminDatabaseLayout(
                    instance_id="native-" + os.environ["SLURM_JOB_ID"],
                    node_root=str(root),
                    state_root=str(state),
                    image_path=str(image),
                    image_sha256=IMAGE_SHA,
                    apptainer="/usr/bin/apptainer",
                )
                database = AdminDatabase(layout, commands)
                baseline = database.save(guard(60))
                persisted = AdminDatabaseSnapshot.model_validate_json(
                    baseline.model_dump_json()
                )
                # Record the real fixed producer format before mutation. Synthetic
                # content-reader fixtures cannot establish this client boundary.
                dump = state / "framework-db-baseline.sql"
                with dump.open("rb") as stream:
                    first_lines = [stream.readline(512) for _ in range(2)]
                    assert all(line.endswith(b"\n") for line in first_lines)
                    stream.seek(max(0, baseline.size_bytes - 512))
                    last_line = stream.read(512).splitlines()[-1]
                facts["native_dump_format"] = {
                    "first_lines": [line.decode("ascii") for line in first_lines],
                    "last_line": last_line.decode("ascii"),
                    "snapshot": baseline.model_dump(mode="json"),
                    "mysqldump_client_version": commands.run(
                        base + ("/usr/bin/mysqldump", "--version"), guard(30)
                    ).decode("ascii"),
                }
                sql(
                    "$p->exec(\"UPDATE framework_snapshot_probe SET value='changed'\");$p->exec('CREATE TABLE framework_snapshot_extra (id INT)');"
                )
                assert (
                    sql(
                        "echo $p->query('SELECT value FROM framework_snapshot_probe')->fetchColumn();"
                    )
                    == b"changed"
                )
                restored = AdminDatabase(layout, commands).restore(persisted, guard(60))
                assert (
                    sql(
                        "echo $p->query('SELECT value FROM framework_snapshot_probe')->fetchColumn();"
                    )
                    == b"original"
                )
                assert (
                    sql(
                        "echo $p->query('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')->fetchColumn();"
                    )
                    == count
                )
                assert (
                    sql(
                        "echo $p->query(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='framework_snapshot_extra'\")->fetchColumn();"
                    )
                    == b"0"
                )
                with pytest.raises(CommandFailure):
                    database.save(guard(30))
                dump = state / "framework-db-baseline.sql"
                assert hashlib.sha256(dump.read_bytes()).hexdigest() == baseline.sha256
                with dump.open("ab") as altered_stream:
                    altered_stream.write(b"\n-- altered")
                sql(
                    "$p->exec(\"UPDATE framework_snapshot_probe SET value='untouched'\");"
                )
                with pytest.raises(CommandFailure):
                    database.restore(persisted, guard(30))
                assert (
                    sql(
                        "echo $p->query('SELECT value FROM framework_snapshot_probe')->fetchColumn();"
                    )
                    == b"untouched"
                )
                assert dump.exists() and not (state / "reset-client.cnf").exists()
                facts.update(
                    snapshot=baseline.model_dump(mode="json"),
                    restore=restored.model_dump(mode="json"),
                    original_table_count=int(count),
                    repeated_save_rejected=True,
                    corrupt_restore_rejected_before_mutation=True,
                    new_table_removed=True,
                    original_value_restored=True,
                    extra_credential_file_created=False,
                    passed=True,
                )
            finally:
                if server is not None:
                    if server.poll() is None:
                        os.killpg(server.pid, signal.SIGTERM)
                        try:
                            server.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                    termination, cleanup = finish_process(
                        server, succeeded=server.returncode is not None, reap_timeout=5
                    )
                    facts["server_termination"] = asdict(termination)
                    facts["server_cleanup_errors"] = [
                        type(error).__name__ for error in cleanup
                    ]
                    if cleanup or termination.state != "reaped":
                        facts["passed"] = False
                facts["seconds"] = time.monotonic() - started
                (output / "admin-database-native.json").write_text(
                    json.dumps(facts, ensure_ascii=False, indent=2) + "\n"
                )
        assert facts["passed"] and not facts["server_cleanup_errors"]
