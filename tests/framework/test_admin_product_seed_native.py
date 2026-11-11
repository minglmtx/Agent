"""Actual original-image product creation and rejection, within one service boot."""

from typing import Any
import json
import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.service_commands import container
from lab_generate_skill.sites.shopping_admin.tasks.product_seed import AdminProductSeed
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_program import (
    PRODUCT_SEED_PHP,
)
from test_admin_services_native import run_admin_services_probe
from test_admin_description_inputs import FIXTURE, load
from test_admin_product_seed import seed
from test_slurm_commands import guard

PROTECTED_ENTITIES = r"""
$e=include '/state/app/app/etc/env.php';$d=$e['db']['connection']['default'];
$p=new PDO('mysql:unix_socket=/state/run/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$rows=$p->query('SELECT * FROM catalog_product_entity WHERE entity_id<>2041 ORDER BY entity_id')->fetchAll(PDO::FETCH_ASSOC);
echo hash('sha256',json_encode($rows,JSON_THROW_ON_ERROR));
"""


def product_probe(
    service: AdminServiceSpec, commands: NativeCommands
) -> dict[str, Any]:
    task = load(FIXTURE.read_bytes()).private_spec
    fixture = seed()
    base = container(service)
    original = commands.run(base + ("php", "-r", PROTECTED_ENTITIES), guard(20))
    worker = AdminProductSeed(service, task, fixture, commands)
    initial = worker.initialize(guard(60))
    assert initial.product_id == 2041 and initial.sku == "TRAIN-sony-headphones"
    assert initial.description in (None, "") and task.description != initial.description
    assert worker.inspect(guard(30)) == initial
    progress = {
        "initial_state": initial.model_dump(mode="json"),
        "initial_readback_equal": True,
    }
    progress_path = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "admin-product-progress.json"
    )
    progress_path.write_text(json.dumps(progress, indent=2) + "\n")
    with pytest.raises(RuntimeError, match="already attempted"):
        worker.initialize(guard(10))
    # Another Python object cannot overwrite the original SKU/ID either.
    duplicate = AdminProductSeed(service, task, fixture, commands)
    with pytest.raises(CommandFailure) as rejected:
        duplicate.initialize(guard(45))
    capture = rejected.value.capture
    progress["duplicate_command"] = {
        "returncode": capture.returncode,
        "stdout_hex": capture.stdout.hex(),
        "stderr_hex": capture.stderr.hex(),
    }
    progress_path.write_text(json.dumps(progress, indent=2) + "\n")
    assert capture.returncode == 2
    assert b"already exists" in rejected.value.capture.stderr
    assert duplicate.inspect(guard(30)) == initial
    after = commands.run(base + ("php", "-r", PROTECTED_ENTITIES), guard(20))
    assert after == original
    return dict(
        initial_state=initial.model_dump(mode="json"),
        fixture_reference=fixture.reference.model_dump(mode="json"),
        native_contract_reference=task.native_contract_ref.model_dump(mode="json"),
        same_object_repeat_rejected=True,
        new_object_overwrite_rejected=True,
        existing_catalog_product_entity_rows_unchanged=True,
        original_entity_rows_sha256=original.decode(),
        goal_description_prefilled=False,
        formal_task_admission=False,
    )


def test_real_declared_product_seed_preserves_original_rows_and_rejects_overwrite() -> (
    None
):
    run_admin_services_probe(
        product_probe, programs=(PRODUCT_SEED_PHP, PROTECTED_ENTITIES)
    )
