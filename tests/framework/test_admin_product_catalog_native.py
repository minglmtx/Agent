"""New private DB: exact legacy projection and selected mutation controls only."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.service_commands import container
from lab_generate_skill.sites.shopping_admin.product_catalog import (
    capture_product_catalog,
)
from lab_generate_skill.sites.shopping_admin.product_catalog_contract import (
    ProductCatalogState,
)
from lab_generate_skill.sites.shopping_admin.product_catalog_program import (
    PRODUCT_CATALOG_PHP,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_seed import AdminProductSeed
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_program import (
    PRODUCT_SEED_PHP,
)
from test_admin_product_seed import seed
from test_admin_description_inputs import FIXTURE, load
from test_admin_services_native import run_admin_services_probe
from test_slurm_commands import guard

LEGACY = Path(__file__).parent / "fixtures/admin-legacy-product-probe.php"

REFERENCE = r"""
ob_start();require '/legacy-probe.php';$raw=ob_get_clean();
$state=json_decode($raw,true,512,JSON_THROW_ON_ERROR);
if (isset($state['records_error'])||!isset($state['records']['product'])||!empty($state['record_errors']['category_product'])) throw new RuntimeException('Original record projection unavailable');
$other=[];$target=null;
foreach ($state['records']['product'] as $row) {
 ksort($row,SORT_STRING);
 if ((int)$row['entity_id']===2041) $target=$row; else $other[]=$row;
}
$flags=JSON_THROW_ON_ERROR|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES;
echo json_encode(['schema_version'=>'admin-product-catalog-state/1','projection'=>'legacy-admin-product-records-v1','product_id'=>2041,'store_id'=>0,'target_record_json'=>$target===null?null:json_encode($target,$flags),'other_product_count'=>count($other),'other_products_sha256'=>hash('sha256',json_encode($other,$flags))],$flags);
"""

MUTATE = r"""
$e=include '/state/app/app/etc/env.php';$d=$e['db']['connection']['default'];
$p=new PDO('mysql:unix_socket=/state/run/mysql.sock;dbname='.$d['dbname'].';charset=utf8mb4',$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$mode=$argv[1];
if ($mode==='target') {
 $attr=$p->query("SELECT a.attribute_id FROM eav_attribute a JOIN eav_entity_type t ON t.entity_type_id=a.entity_type_id WHERE t.entity_type_code='catalog_product' AND a.attribute_code='description'")->fetchColumn();
 $s=$p->prepare('INSERT INTO catalog_product_entity_text (attribute_id,store_id,entity_id,value) VALUES (?,0,2041,?) ON DUPLICATE KEY UPDATE value=VALUES(value)');
 $s->execute([$attr,'<p>Catalog target control only</p>']);echo 'target';
} elseif ($mode==='other') {
 $id=$p->query('SELECT MIN(product_id) FROM cataloginventory_stock_item WHERE product_id<>2041')->fetchColumn();
 $s=$p->prepare('SELECT qty FROM cataloginventory_stock_item WHERE product_id=?');$s->execute([$id]);$old=$s->fetchAll(PDO::FETCH_COLUMN);
 if (count($old)!==1) throw new RuntimeException('Ambiguous other stock control');
 $s=$p->prepare('UPDATE cataloginventory_stock_item SET qty=qty+1 WHERE product_id=?');$s->execute([$id]);
 echo json_encode(['product_id'=>(int)$id,'qty'=>(string)$old[0]],JSON_THROW_ON_ERROR);
} elseif ($mode==='restore-other') {
 $old=json_decode($argv[2],true,512,JSON_THROW_ON_ERROR);
 if (!is_int($old['product_id'])||$old['product_id']<=0||$old['product_id']===2041||!is_string($old['qty'])) throw new RuntimeException('Invalid original control');
 $s=$p->prepare('UPDATE cataloginventory_stock_item SET qty=? WHERE product_id=?');$s->execute([$old['qty'],$old['product_id']]);echo 'restored';
} else throw new RuntimeException('Invalid controlled operation');
"""


def validate_legacy_input() -> None:
    declared = json.loads(
        LEGACY.with_name("admin-legacy-product-probe-source.json").read_text()
    )
    assert hashlib.sha256(LEGACY.read_bytes()).hexdigest() == declared["sha256"]
    assert LEGACY.read_bytes().startswith(b"<?php\n")


def test_registered_legacy_probe_input() -> None:
    validate_legacy_input()


def catalog_probe(
    service: AdminServiceSpec, commands: NativeCommands
) -> dict[str, Any]:
    validate_legacy_input()
    task = load(FIXTURE.read_bytes()).private_spec
    base = container(service)
    reference_base = base[:-1] + (
        "--bind",
        str(LEGACY) + ":/legacy-probe.php:ro",
        base[-1],
    )
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "product-catalog-controls"
    output.mkdir()

    def read(name: str) -> ProductCatalogState:
        actual = capture_product_catalog(service, task.product_id, commands, guard(40))
        (output / (name + ".json")).write_text(actual.model_dump_json())
        return actual

    def legacy(name: str) -> ProductCatalogState:
        raw = commands.run(reference_base + ("php", "-r", REFERENCE), guard(45))
        (output / (name + "-legacy.json")).write_bytes(raw)
        return ProductCatalogState.model_validate_json(raw)

    absent = read("absent")
    assert absent.target_record_json is None
    AdminProductSeed(service, task, seed(), commands).initialize(guard(60))
    initial = read("initial")
    assert initial.target_record_json is not None
    assert initial.other_product_count == absent.other_product_count
    assert initial.other_products_sha256 == absent.other_products_sha256
    assert initial == legacy("initial")
    commands.run(base + ("php", "-r", MUTATE, "target"), guard(20))
    target = read("target")
    assert target.target_record_json != initial.target_record_json
    assert target.other_products_sha256 == initial.other_products_sha256
    assert target == legacy("target")
    old = commands.run(base + ("php", "-r", MUTATE, "other"), guard(20))
    (output / "other-original.json").write_bytes(old)
    other = read("other")
    assert other.target_record_json == target.target_record_json
    assert other.other_product_count == target.other_product_count
    assert other.other_products_sha256 != target.other_products_sha256
    assert other == legacy("other")
    commands.run(base + ("php", "-r", MUTATE, "restore-other", old.decode()), guard(20))
    restored = read("restored-other")
    assert restored == target
    return dict(
        legacy_projection_equal=True,
        target_change_preserves_other_digest=True,
        other_change_detected=True,
        other_control_restored=True,
        original_absent_distinct=True,
        raw_other_records_preserved=False,
        whole_database_coverage=False,
        formal_task_admission=False,
        evidence=str(output),
    )


def test_real_private_catalog_projection_and_protection() -> None:
    run_admin_services_probe(
        catalog_probe,
        programs=(PRODUCT_SEED_PHP, PRODUCT_CATALOG_PHP, REFERENCE, MUTATE),
    )
