"""Fresh private MySQL fixtures; setup and original-namespace cleanup only."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import traceback
from typing import Any, Iterator
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.pid_namespace import HeldPidNamespace
from lab_generate_skill.sites.shopping_admin.database_contract import (
    AdminDatabaseLayout,
)
from lab_generate_skill.sites.shopping_admin.service_contract import (
    AdminPorts,
    AdminServiceSpec,
)
from lab_generate_skill.sites.shopping_admin.service_commands import container
from lab_generate_skill.sites.shopping_admin.database_observer import prepare_observer
from test_admin_database_native import IMAGE, IMAGE_SHA, PDO
from test_slurm_commands import guard


@pytest.fixture(scope="module")
def observer_image() -> Iterator[Path]:
    assert os.environ.get("SLURM_JOB_ID")
    root = Path(tempfile.mkdtemp(prefix="lab-observer-image-", dir="/tmp"))
    image = root / "admin.sif"
    shutil.copyfile(IMAGE, image)
    digest = hashlib.sha256()
    with image.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    assert digest.hexdigest() == IMAGE_SHA
    image.chmod(0o400)
    yield image
    shutil.rmtree(root)


class NativeDatabase:
    def __init__(self, image: Path, scenario: str) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="lab-observer-db-", dir="/tmp"))
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        # A private copy avoids symlinks and preserves the production layout contract.
        shutil.copyfile(image, self.root / "admin.sif")
        (self.root / "admin.sif").chmod(0o400)
        self.spec = AdminServiceSpec(
            layout=AdminDatabaseLayout(
                instance_id="observer-" + scenario,
                node_root=str(self.root),
                state_root=str(self.state),
                image_path=str(self.root / "admin.sif"),
                image_sha256=IMAGE_SHA,
                apptainer="/usr/bin/apptainer",
            ),
            ports=AdminPorts(
                web=12001, database=12002, redis=12003, search=12004, transport=12005
            ),
        )
        self.commands = CheckedNativeCommands(
            ProcessRunner(max_output_bytes=128 * 1024)
        )
        self.output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / (
            "observer-" + scenario
        )
        self.output.mkdir()
        self.server: subprocess.Popen[bytes] | None = None
        self.held: HeldPidNamespace | None = None
        self.facts: dict[str, Any] = {
            "passed": False,
            "root": str(self.root),
            "image_sha256": IMAGE_SHA,
            "engineering_only": True,
            "whole_resource_closure_verified": False,
            "cleanup_errors": [],
        }

    def run(self, program: str) -> bytes:
        return self.commands.run(
            container(self.spec) + ("php", "-r", program), guard(20)
        )

    def seed(self) -> None:
        self.commands.run(
            container(self.spec, seeded=False)
            + (
                "sh",
                "-ec",
                "cp -a /var/lib/mysql /state/mysql; chmod -R u+rwX /state/mysql; "
                "mkdir -p /state/run /state/app/app/etc /state/elasticsearch/config /state/elasticsearch/data /state/elasticsearch/logs; "
                "cp /var/www/magento2/app/etc/env.php /state/app/app/etc/env.php",
            ),
            guard(90),
        )

    def start(self, scenario: str) -> None:
        if scenario == "missing_account":
            self.run(
                "$f='/state/app/app/etc/env.php';$e=include $f;$e['db']['connection']['default']['username']='framework_missing_account';file_put_contents($f,'<?php return '.var_export($e,true).';');"
            )
        if scenario != "no_process":
            prepare_observer(self.spec, self.commands, guard(20))
        if scenario == "broken_init":
            (self.state / "database-observer-init.sql").write_text(
                "INVALID FRAMEWORK INITIALIZATION;\n"
            )
        args = container(self.spec) + (
            "mysqld",
            "--no-defaults",
            "--datadir=/state/mysql",
            "--socket=/state/run/mysql.sock",
            "--pid-file=/state/run/mysql.pid",
            "--skip-networking",
            "--innodb-buffer-pool-size=128M",
        )
        if scenario != "no_process":
            args += ("--init-file=/state/database-observer-init.sql",)
        with (self.output / "mysql.log").open("wb") as log:
            self.server = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
        ready = guard(40)
        while not (self.state / "run/mysql.sock").is_socket():
            if self.server.poll() is not None:
                self.facts["startup_exit"] = self.server.returncode
                return
            ready.wait(0.1)
        self.held = HeldPidNamespace("mysql", self.server, guard(10))
        # Socket availability is not the assertion of credentials or PROCESS.
        self.facts["original_namespace"] = self.held.identity.model_dump(mode="json")

    def finish(self) -> None:
        errors: list[str] = []
        if self.held is not None:
            try:
                self.facts["stop"] = self.held.stop(guard(10)).model_dump(mode="json")
            except BaseException:
                errors.append(traceback.format_exc())
            finally:
                try:
                    self.held.close()
                except BaseException:
                    errors.append(traceback.format_exc())
        elif self.server is not None:
            self.facts["unheld_server_returncode"] = self.server.poll()
            if self.server.returncode is None:
                errors.append("Original namespace was not pinned; retain isolated root")
        self.facts["cleanup_errors"] = errors
        (self.output / "result.json").write_text(
            json.dumps(self.facts, indent=2) + "\n"
        )
        if errors:
            raise RuntimeError("Private MySQL cleanup unconfirmed; inspect result")
        if self.facts["passed"]:
            shutil.rmtree(self.root)


@contextmanager
def database(image: Path, scenario: str) -> Iterator[NativeDatabase]:
    db = NativeDatabase(image, scenario)
    try:
        db.seed()
        yield db
        db.facts["passed"] = True
    except BaseException as error:
        (db.output / "traceback.txt").write_text(traceback.format_exc())
        capture = getattr(error, "capture", None)
        if capture is not None:
            (db.output / "native-stderr.bin").write_bytes(capture.stderr)
        raise
    finally:
        db.finish()
